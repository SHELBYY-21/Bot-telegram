"""SQLite ledger — durable store for CE VAULT operations."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ce_vault.models import ReceiverProfile, Transaction, utc_now
from ce_vault.theme import TxStatus

SCHEMA = """
CREATE TABLE IF NOT EXISTS ledgers (
    id TEXT PRIMARY KEY,
    slip_hash TEXT,
    ocr_json TEXT,
    receiver_name TEXT,
    bank TEXT,
    last4 TEXT,
    thb REAL NOT NULL DEFAULT 0,
    usdt REAL NOT NULL DEFAULT 0,
    buy_rate REAL NOT NULL DEFAULT 0,
    sell_rate REAL NOT NULL DEFAULT 0,
    profit_pct REAL NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 0,
    staff_id INTEGER,
    staff_name TEXT,
    chat_id INTEGER,
    image_file_id TEXT,
    status TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    settled_at TEXT,
    deleted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_ledgers_slip_hash ON ledgers(slip_hash);
CREATE INDEX IF NOT EXISTS idx_ledgers_receiver ON ledgers(bank, last4);
CREATE INDEX IF NOT EXISTS idx_ledgers_status ON ledgers(status);
CREATE INDEX IF NOT EXISTS idx_ledgers_chat ON ledgers(chat_id);

CREATE TABLE IF NOT EXISTS receivers (
    key TEXT PRIMARY KEY,
    bank TEXT NOT NULL,
    last4 TEXT NOT NULL,
    name TEXT,
    tx_count INTEGER NOT NULL DEFAULT 0,
    total_thb REAL NOT NULL DEFAULT 0,
    total_usdt REAL NOT NULL DEFAULT 0,
    first_seen TEXT,
    last_seen TEXT,
    risk TEXT NOT NULL DEFAULT 'LOW'
);

CREATE TABLE IF NOT EXISTS vault_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def new_ledger_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = uuid.uuid4().hex[:6].upper()
    return f"LV-{stamp}-{suffix}"


class Ledger:
    """Thread-safe SQLite ledger with receiver history rollups."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        self._ensure_balance()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _ensure_balance(self) -> None:
        row = self._conn.execute(
            "SELECT value FROM vault_meta WHERE key = 'balance_usdt'"
        ).fetchone()
        if not row:
            self._conn.execute(
                "INSERT INTO vault_meta(key, value) VALUES ('balance_usdt', '0')"
            )
            self._conn.commit()

    def get_balance(self) -> float:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM vault_meta WHERE key = 'balance_usdt'"
            ).fetchone()
            return float(row["value"]) if row else 0.0

    def set_balance(self, value: float) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO vault_meta(key, value) VALUES ('balance_usdt', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(round(value, 4)),),
            )
            self._conn.commit()

    def adjust_balance(self, delta_usdt: float) -> float:
        with self._lock:
            bal = self.get_balance() + delta_usdt
            self.set_balance(bal)
            return bal

    def create(self, tx: Transaction) -> Transaction:
        with self._lock:
            now = utc_now()
            tx.created_at = tx.created_at or now
            tx.updated_at = now
            self._conn.execute(
                """
                INSERT INTO ledgers (
                    id, slip_hash, ocr_json, receiver_name, bank, last4,
                    thb, usdt, buy_rate, sell_rate, profit_pct, confidence,
                    staff_id, staff_name, chat_id, image_file_id, status, notes,
                    created_at, updated_at, settled_at, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tx.ledger_id,
                    tx.slip_hash or None,
                    json.dumps(tx.ocr or {}, ensure_ascii=False),
                    tx.receiver_name,
                    tx.bank,
                    tx.last4,
                    tx.thb,
                    tx.usdt,
                    tx.buy_rate,
                    tx.sell_rate,
                    tx.profit_pct,
                    tx.confidence,
                    tx.staff_id,
                    tx.staff_name,
                    tx.chat_id,
                    tx.image_file_id,
                    tx.status,
                    tx.notes,
                    tx.created_at,
                    tx.updated_at,
                    tx.settled_at,
                    tx.deleted_at,
                ),
            )
            self._conn.commit()
            return tx

    def get(self, ledger_id: str) -> Transaction | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM ledgers WHERE id = ?", (ledger_id,)
            ).fetchone()
            return Transaction.from_row(dict(row)) if row else None

    def update(self, tx: Transaction) -> Transaction:
        with self._lock:
            tx.updated_at = utc_now()
            self._conn.execute(
                """
                UPDATE ledgers SET
                    slip_hash=?, ocr_json=?, receiver_name=?, bank=?, last4=?,
                    thb=?, usdt=?, buy_rate=?, sell_rate=?, profit_pct=?, confidence=?,
                    staff_id=?, staff_name=?, chat_id=?, image_file_id=?, status=?, notes=?,
                    updated_at=?, settled_at=?, deleted_at=?
                WHERE id=?
                """,
                (
                    tx.slip_hash or None,
                    json.dumps(tx.ocr or {}, ensure_ascii=False),
                    tx.receiver_name,
                    tx.bank,
                    tx.last4,
                    tx.thb,
                    tx.usdt,
                    tx.buy_rate,
                    tx.sell_rate,
                    tx.profit_pct,
                    tx.confidence,
                    tx.staff_id,
                    tx.staff_name,
                    tx.chat_id,
                    tx.image_file_id,
                    tx.status,
                    tx.notes,
                    tx.updated_at,
                    tx.settled_at,
                    tx.deleted_at,
                    tx.ledger_id,
                ),
            )
            self._conn.commit()
            return tx

    def find_by_slip_hash(self, slip_hash: str) -> Transaction | None:
        if not slip_hash:
            return None
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM ledgers WHERE slip_hash = ? AND deleted_at IS NULL "
                "ORDER BY created_at DESC LIMIT 1",
                (slip_hash,),
            ).fetchone()
            return Transaction.from_row(dict(row)) if row else None

    def open_count(self, chat_id: int | None = None) -> int:
        with self._lock:
            open_statuses = (
                TxStatus.RECEIVED.value,
                TxStatus.OCR_VERIFIED.value,
                TxStatus.WAITING_USDT.value,
                TxStatus.EDITING.value,
            )
            placeholders = ",".join("?" * len(open_statuses))
            sql = (
                f"SELECT COUNT(*) AS c FROM ledgers WHERE status IN ({placeholders}) "
                "AND deleted_at IS NULL"
            )
            params: list[Any] = list(open_statuses)
            if chat_id is not None:
                sql += " AND chat_id = ?"
                params.append(chat_id)
            row = self._conn.execute(sql, params).fetchone()
            return int(row["c"])

    def settled_today_count(self, chat_id: int | None = None) -> int:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._lock:
            sql = (
                "SELECT COUNT(*) AS c FROM ledgers WHERE status = ? "
                "AND deleted_at IS NULL AND settled_at LIKE ?"
            )
            params: list[Any] = [TxStatus.SETTLED.value, f"{day}%"]
            if chat_id is not None:
                sql += " AND chat_id = ?"
                params.append(chat_id)
            row = self._conn.execute(sql, params).fetchone()
            return int(row["c"])

    def settle(self, ledger_id: str) -> tuple[Transaction, float]:
        with self._lock:
            tx = self.get(ledger_id)
            if not tx:
                raise KeyError(ledger_id)
            if tx.status == TxStatus.SETTLED.value:
                return tx, self.get_balance()
            tx.status = TxStatus.SETTLED.value
            tx.settled_at = utc_now()
            self.update(tx)
            balance = self.adjust_balance(tx.usdt)
            self._upsert_receiver(tx)
            return tx, balance

    def soft_delete(self, ledger_id: str) -> Transaction:
        with self._lock:
            tx = self.get(ledger_id)
            if not tx:
                raise KeyError(ledger_id)
            tx.status = TxStatus.DELETED.value
            tx.deleted_at = utc_now()
            return self.update(tx)

    def receiver_profile(self, bank: str, last4: str) -> ReceiverProfile | None:
        key = f"{bank}:{last4}".upper()
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM receivers WHERE key = ?", (key,)
            ).fetchone()
            if not row:
                return None
            return ReceiverProfile(
                bank=row["bank"],
                last4=row["last4"],
                name=row["name"] or "",
                tx_count=int(row["tx_count"]),
                total_thb=float(row["total_thb"]),
                total_usdt=float(row["total_usdt"]),
                first_seen=row["first_seen"] or "",
                last_seen=row["last_seen"] or "",
                risk=row["risk"] or "LOW",
            )

    def receiver_tx_count(self, bank: str, last4: str) -> int:
        profile = self.receiver_profile(bank, last4)
        if profile:
            return profile.tx_count
        # Include unsettled matches too for "repeated receiver" warnings
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS c FROM ledgers WHERE bank = ? AND last4 = ? "
                "AND deleted_at IS NULL",
                (bank, last4),
            ).fetchone()
            return int(row["c"])

    def _upsert_receiver(self, tx: Transaction) -> None:
        if not tx.bank or not tx.last4:
            return
        key = f"{tx.bank}:{tx.last4}".upper()
        now = utc_now()
        existing = self._conn.execute(
            "SELECT * FROM receivers WHERE key = ?", (key,)
        ).fetchone()
        if existing:
            tx_count = int(existing["tx_count"]) + 1
            risk = _risk_for_count(tx_count)
            self._conn.execute(
                """
                UPDATE receivers SET
                    name = COALESCE(NULLIF(?, ''), name),
                    tx_count = ?,
                    total_thb = total_thb + ?,
                    total_usdt = total_usdt + ?,
                    last_seen = ?,
                    risk = ?
                WHERE key = ?
                """,
                (tx.receiver_name, tx_count, tx.thb, tx.usdt, now, risk, key),
            )
        else:
            self._conn.execute(
                """
                INSERT INTO receivers (
                    key, bank, last4, name, tx_count, total_thb, total_usdt,
                    first_seen, last_seen, risk
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    tx.bank,
                    tx.last4,
                    tx.receiver_name,
                    tx.thb,
                    tx.usdt,
                    now,
                    now,
                    "LOW",
                ),
            )
        self._conn.commit()


def _risk_for_count(tx_count: int) -> str:
    if tx_count >= 40:
        return "HIGH"
    if tx_count >= 15:
        return "MED"
    return "LOW"
