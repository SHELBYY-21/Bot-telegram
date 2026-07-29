"""SQLite ledger — durable store for CE VAULT operations."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from vault.models import ReceiverHistory, Transaction, TxStatus, utcnow

DB_PATH = Path(os.environ.get("LEDGER_DB", "ledger.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    ledger_id     TEXT PRIMARY KEY,
    status        TEXT NOT NULL,
    thb           REAL,
    usdt          REAL,
    buy_rate      REAL,
    sell_rate     REAL,
    profit_pct    REAL,
    receiver      TEXT,
    bank          TEXT,
    last4         TEXT,
    staff         TEXT,
    staff_id      INTEGER,
    chat_id       INTEGER,
    message_id    INTEGER,
    slip_file_id  TEXT,
    slip_hash     TEXT,
    ocr_confidence REAL,
    ocr_json      TEXT,
    notes         TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    settled_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_tx_last4 ON transactions(last4);
CREATE INDEX IF NOT EXISTS idx_tx_receiver ON transactions(receiver);
CREATE INDEX IF NOT EXISTS idx_tx_slip_hash ON transactions(slip_hash);
CREATE INDEX IF NOT EXISTS idx_tx_status ON transactions(status);
CREATE INDEX IF NOT EXISTS idx_tx_created ON transactions(created_at);

CREATE TABLE IF NOT EXISTS balance (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    usdt REAL NOT NULL DEFAULT 0,
    thb  REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Ledger:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else DB_PATH
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._db() as conn:
            conn.executescript(SCHEMA)
            row = conn.execute("SELECT id FROM balance WHERE id = 1").fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO balance (id, usdt, thb, updated_at) VALUES (1, 0, 0, ?)",
                    (utcnow(),),
                )

    def upsert(self, tx: Transaction) -> Transaction:
        tx.touch()
        payload = (
            tx.ledger_id,
            tx.status,
            tx.thb,
            tx.usdt,
            tx.buy_rate,
            tx.sell_rate,
            tx.profit_pct,
            tx.receiver,
            tx.bank,
            tx.last4,
            tx.staff,
            tx.staff_id,
            tx.chat_id,
            tx.message_id,
            tx.slip_file_id,
            tx.slip_hash,
            tx.ocr_confidence,
            json.dumps(tx.ocr) if tx.ocr is not None else None,
            tx.notes,
            tx.created_at,
            tx.updated_at,
            tx.settled_at,
        )
        with self._db() as conn:
            conn.execute(
                """
                INSERT INTO transactions (
                    ledger_id, status, thb, usdt, buy_rate, sell_rate, profit_pct,
                    receiver, bank, last4, staff, staff_id, chat_id, message_id,
                    slip_file_id, slip_hash, ocr_confidence, ocr_json, notes,
                    created_at, updated_at, settled_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ledger_id) DO UPDATE SET
                    status=excluded.status,
                    thb=excluded.thb,
                    usdt=excluded.usdt,
                    buy_rate=excluded.buy_rate,
                    sell_rate=excluded.sell_rate,
                    profit_pct=excluded.profit_pct,
                    receiver=excluded.receiver,
                    bank=excluded.bank,
                    last4=excluded.last4,
                    staff=excluded.staff,
                    staff_id=excluded.staff_id,
                    chat_id=excluded.chat_id,
                    message_id=excluded.message_id,
                    slip_file_id=excluded.slip_file_id,
                    slip_hash=excluded.slip_hash,
                    ocr_confidence=excluded.ocr_confidence,
                    ocr_json=excluded.ocr_json,
                    notes=excluded.notes,
                    updated_at=excluded.updated_at,
                    settled_at=excluded.settled_at
                """,
                payload,
            )
        return tx

    def get(self, ledger_id: str) -> Transaction | None:
        with self._db() as conn:
            row = conn.execute(
                "SELECT * FROM transactions WHERE ledger_id = ?", (ledger_id,)
            ).fetchone()
        return self._row_to_tx(row) if row else None

    def delete(self, ledger_id: str) -> bool:
        with self._db() as conn:
            cur = conn.execute(
                "DELETE FROM transactions WHERE ledger_id = ?", (ledger_id,)
            )
            return cur.rowcount > 0

    def find_by_slip_hash(self, slip_hash: str) -> Transaction | None:
        if not slip_hash:
            return None
        with self._db() as conn:
            row = conn.execute(
                "SELECT * FROM transactions WHERE slip_hash = ? ORDER BY created_at DESC LIMIT 1",
                (slip_hash,),
            ).fetchone()
        return self._row_to_tx(row) if row else None

    def receiver_history(
        self, *, last4: str | None = None, receiver: str | None = None
    ) -> ReceiverHistory | None:
        clauses: list[str] = ["status = ?"]
        params: list[Any] = [TxStatus.SETTLED.value]
        if last4:
            clauses.append("last4 = ?")
            params.append(last4[-4:])
        if receiver:
            clauses.append("receiver = ?")
            params.append(receiver)
        if len(clauses) == 1 and not last4 and not receiver:
            return None
        where = " AND ".join(clauses)
        with self._db() as conn:
            row = conn.execute(
                f"""
                SELECT
                    COALESCE(MAX(receiver), '') AS receiver,
                    MAX(bank) AS bank,
                    MAX(last4) AS last4,
                    COUNT(*) AS tx_count,
                    COALESCE(SUM(thb), 0) AS total_thb,
                    COALESCE(SUM(usdt), 0) AS total_usdt,
                    MIN(created_at) AS first_seen,
                    MAX(created_at) AS last_seen
                FROM transactions
                WHERE {where}
                """,
                params,
            ).fetchone()
        if not row or row["tx_count"] == 0:
            return None
        risk = self._risk(row["tx_count"], row["total_thb"])
        return ReceiverHistory(
            receiver=row["receiver"] or "Unknown",
            bank=row["bank"],
            last4=row["last4"],
            tx_count=int(row["tx_count"]),
            total_thb=float(row["total_thb"]),
            total_usdt=float(row["total_usdt"]),
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
            risk=risk,
        )

    def has_receiver(self, last4: str | None = None, receiver: str | None = None) -> bool:
        hist = self.receiver_history(last4=last4, receiver=receiver)
        return hist is not None and hist.tx_count > 0

    def recent(self, limit: int = 10) -> list[Transaction]:
        with self._db() as conn:
            rows = conn.execute(
                "SELECT * FROM transactions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_tx(r) for r in rows]

    def get_balance(self) -> dict[str, float]:
        with self._db() as conn:
            row = conn.execute("SELECT usdt, thb FROM balance WHERE id = 1").fetchone()
        return {"usdt": float(row["usdt"]), "thb": float(row["thb"])}

    def set_balance(self, *, usdt: float | None = None, thb: float | None = None) -> dict[str, float]:
        current = self.get_balance()
        next_usdt = float(usdt) if usdt is not None else current["usdt"]
        next_thb = float(thb) if thb is not None else current["thb"]
        with self._db() as conn:
            conn.execute(
                "UPDATE balance SET usdt = ?, thb = ?, updated_at = ? WHERE id = 1",
                (next_usdt, next_thb, utcnow()),
            )
        return {"usdt": next_usdt, "thb": next_thb}

    def apply_settlement(self, tx: Transaction) -> dict[str, float]:
        """Debit USDT inventory and credit THB on settle."""
        bal = self.get_balance()
        usdt = bal["usdt"] - float(tx.usdt or 0)
        thb = bal["thb"] + float(tx.thb or 0)
        return self.set_balance(usdt=usdt, thb=thb)

    @staticmethod
    def _risk(tx_count: int, total_thb: float) -> str:
        if tx_count >= 100 or total_thb >= 5_000_000:
            return "HIGH"
        if tx_count >= 20 or total_thb >= 500_000:
            return "MED"
        return "LOW"

    @staticmethod
    def _row_to_tx(row: sqlite3.Row) -> Transaction:
        ocr = None
        if row["ocr_json"]:
            try:
                ocr = json.loads(row["ocr_json"])
            except json.JSONDecodeError:
                ocr = None
        return Transaction(
            ledger_id=row["ledger_id"],
            status=row["status"],
            thb=row["thb"],
            usdt=row["usdt"],
            buy_rate=row["buy_rate"],
            sell_rate=row["sell_rate"],
            profit_pct=row["profit_pct"],
            receiver=row["receiver"],
            bank=row["bank"],
            last4=row["last4"],
            staff=row["staff"],
            staff_id=row["staff_id"],
            chat_id=row["chat_id"],
            message_id=row["message_id"],
            slip_file_id=row["slip_file_id"],
            slip_hash=row["slip_hash"],
            ocr_confidence=row["ocr_confidence"],
            ocr=ocr,
            notes=row["notes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            settled_at=row["settled_at"],
        )


def relative_day(iso_ts: str) -> str:
    try:
        dt = datetime.strptime(iso_ts[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return iso_ts[:10]
    today = datetime.now(timezone.utc).date()
    if dt.date() == today:
        return "Today"
    return dt.strftime("%Y-%m-%d")
