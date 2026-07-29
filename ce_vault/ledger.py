"""SQLite ledger — optimized indexes for slip / receiver / status queries."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from ce_vault.design import STATUS_SETTLED
from ce_vault.models import ReceiverHistory, Transaction, utc_now


def new_ledger_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"LD-{stamp}-{uuid.uuid4().hex[:6].upper()}"


class Ledger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._lock, self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS transactions (
                    ledger_id     TEXT PRIMARY KEY,
                    status        TEXT NOT NULL,
                    thb           REAL NOT NULL DEFAULT 0,
                    usdt          REAL NOT NULL DEFAULT 0,
                    buy_rate      REAL NOT NULL DEFAULT 0,
                    sell_rate     REAL NOT NULL DEFAULT 0,
                    profit_pct    REAL NOT NULL DEFAULT 0,
                    profit_thb    REAL NOT NULL DEFAULT 0,
                    receiver_name TEXT NOT NULL DEFAULT '',
                    bank          TEXT NOT NULL DEFAULT '',
                    last4         TEXT NOT NULL DEFAULT '',
                    confidence    REAL NOT NULL DEFAULT 0,
                    slip_hash     TEXT NOT NULL DEFAULT '',
                    slip_ref      TEXT NOT NULL DEFAULT '',
                    staff_id      INTEGER NOT NULL DEFAULT 0,
                    staff_name    TEXT NOT NULL DEFAULT '',
                    chat_id       INTEGER NOT NULL DEFAULT 0,
                    message_id    INTEGER,
                    image_file_id TEXT NOT NULL DEFAULT '',
                    ocr_json      TEXT NOT NULL DEFAULT '{}',
                    note          TEXT NOT NULL DEFAULT '',
                    created_at    TEXT NOT NULL,
                    updated_at    TEXT NOT NULL,
                    settled_at    TEXT NOT NULL DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_tx_status
                    ON transactions(status);
                CREATE INDEX IF NOT EXISTS idx_tx_receiver
                    ON transactions(bank, last4);
                CREATE INDEX IF NOT EXISTS idx_tx_slip_hash
                    ON transactions(slip_hash);
                CREATE INDEX IF NOT EXISTS idx_tx_created
                    ON transactions(created_at);
                CREATE INDEX IF NOT EXISTS idx_tx_chat
                    ON transactions(chat_id);

                CREATE TABLE IF NOT EXISTS vault_meta (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                INSERT OR IGNORE INTO vault_meta(key, value)
                    VALUES ('balance_usdt', '0');
                """
            )

    def _row_to_tx(self, row: sqlite3.Row) -> Transaction:
        return Transaction(**{k: row[k] for k in row.keys()})

    def create(self, tx: Transaction) -> Transaction:
        tx.updated_at = utc_now()
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                INSERT INTO transactions (
                    ledger_id, status, thb, usdt, buy_rate, sell_rate,
                    profit_pct, profit_thb, receiver_name, bank, last4,
                    confidence, slip_hash, slip_ref, staff_id, staff_name,
                    chat_id, message_id, image_file_id, ocr_json, note,
                    created_at, updated_at, settled_at
                ) VALUES (
                    :ledger_id, :status, :thb, :usdt, :buy_rate, :sell_rate,
                    :profit_pct, :profit_thb, :receiver_name, :bank, :last4,
                    :confidence, :slip_hash, :slip_ref, :staff_id, :staff_name,
                    :chat_id, :message_id, :image_file_id, :ocr_json, :note,
                    :created_at, :updated_at, :settled_at
                )
                """,
                tx.to_dict(),
            )
        return tx

    def get(self, ledger_id: str) -> Transaction | None:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM transactions WHERE ledger_id = ?", (ledger_id,)
            ).fetchone()
        return self._row_to_tx(row) if row else None

    def update(self, tx: Transaction) -> Transaction:
        tx.updated_at = utc_now()
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                UPDATE transactions SET
                    status=:status, thb=:thb, usdt=:usdt, buy_rate=:buy_rate,
                    sell_rate=:sell_rate, profit_pct=:profit_pct,
                    profit_thb=:profit_thb, receiver_name=:receiver_name,
                    bank=:bank, last4=:last4, confidence=:confidence,
                    slip_hash=:slip_hash, slip_ref=:slip_ref,
                    staff_id=:staff_id, staff_name=:staff_name,
                    chat_id=:chat_id, message_id=:message_id,
                    image_file_id=:image_file_id, ocr_json=:ocr_json,
                    note=:note, updated_at=:updated_at, settled_at=:settled_at
                WHERE ledger_id=:ledger_id
                """,
                tx.to_dict(),
            )
        return tx

    def delete(self, ledger_id: str) -> bool:
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM transactions WHERE ledger_id = ?", (ledger_id,)
            )
            return cur.rowcount > 0

    def find_by_slip_hash(self, slip_hash: str) -> Transaction | None:
        if not slip_hash:
            return None
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM transactions WHERE slip_hash = ? ORDER BY created_at DESC LIMIT 1",
                (slip_hash,),
            ).fetchone()
        return self._row_to_tx(row) if row else None

    def receiver_history(self, bank: str, last4: str) -> ReceiverHistory:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS tx_count,
                    COALESCE(SUM(thb), 0) AS total_thb,
                    COALESCE(SUM(usdt), 0) AS total_usdt,
                    MIN(created_at) AS first_seen,
                    MAX(created_at) AS last_seen,
                    MAX(receiver_name) AS receiver_name
                FROM transactions
                WHERE bank = ? AND last4 = ? AND status = ?
                """,
                (bank, last4, STATUS_SETTLED),
            ).fetchone()
        count = int(row["tx_count"] or 0)
        risk = "LOW"
        if count >= 50:
            risk = "ELEVATED"
        elif count >= 20:
            risk = "WATCH"
        return ReceiverHistory(
            bank=bank,
            last4=last4,
            receiver_name=row["receiver_name"] or "",
            tx_count=count,
            total_thb=float(row["total_thb"] or 0),
            total_usdt=float(row["total_usdt"] or 0),
            first_seen=row["first_seen"] or "",
            last_seen=row["last_seen"] or "",
            risk=risk,
        )

    def open_count(self) -> int:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM transactions WHERE status != ?",
                (STATUS_SETTLED,),
            ).fetchone()
        return int(row["c"])

    def settled_today_count(self) -> int:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM transactions WHERE settled_at LIKE ?",
                (f"{today}%",),
            ).fetchone()
        return int(row["c"])

    def get_balance(self) -> float:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM vault_meta WHERE key = 'balance_usdt'"
            ).fetchone()
        return float(row["value"]) if row else 0.0

    def set_balance(self, value: float) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO vault_meta(key, value) VALUES('balance_usdt', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(round(value, 4)),),
            )

    def adjust_balance(self, delta_usdt: float) -> float:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM vault_meta WHERE key = 'balance_usdt'"
            ).fetchone()
            current = float(row["value"]) if row else 0.0
            new_bal = round(current + delta_usdt, 4)
            conn.execute(
                "INSERT INTO vault_meta(key, value) VALUES('balance_usdt', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(new_bal),),
            )
        return new_bal

    def recent(self, limit: int = 10) -> list[Transaction]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM transactions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_tx(r) for r in rows]

    def dumps_ocr(self, data: dict) -> str:
        return json.dumps(data, ensure_ascii=False)
