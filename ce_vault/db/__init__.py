"""SQLite ledger store — durable, indexed, single-file."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

from ce_vault.models import ReceiverHistory, Transaction, iso


SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    ledger_id     TEXT PRIMARY KEY,
    status        TEXT NOT NULL,
    thb           REAL,
    usdt          REAL,
    buy_rate      REAL,
    sell_rate     REAL,
    profit_pct    REAL,
    receiver_name TEXT NOT NULL DEFAULT '',
    bank          TEXT NOT NULL DEFAULT '',
    last4         TEXT NOT NULL DEFAULT '',
    confidence    REAL,
    staff         TEXT NOT NULL DEFAULT '',
    staff_id      INTEGER,
    chat_id       INTEGER,
    message_id    INTEGER,
    image_path    TEXT,
    slip_hash     TEXT,
    ocr_json      TEXT,
    notes         TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    settled_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_tx_status ON transactions(status);
CREATE INDEX IF NOT EXISTS idx_tx_slip_hash ON transactions(slip_hash);
CREATE INDEX IF NOT EXISTS idx_tx_receiver ON transactions(bank, last4);
CREATE INDEX IF NOT EXISTS idx_tx_created ON transactions(created_at);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS balance (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    usdt_balance  REAL NOT NULL DEFAULT 0,
    updated_at    TEXT NOT NULL
);
"""


class LedgerStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        self._conn.execute(
            "INSERT OR IGNORE INTO balance (id, usdt_balance, updated_at) VALUES (1, 0, ?)",
            (iso(),),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def upsert(self, tx: Transaction) -> Transaction:
        row = tx.to_row()
        cols = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        updates = ", ".join(f"{k}=excluded.{k}" for k in row if k != "ledger_id")
        sql = (
            f"INSERT INTO transactions ({cols}) VALUES ({placeholders}) "
            f"ON CONFLICT(ledger_id) DO UPDATE SET {updates}"
        )
        self._conn.execute(sql, tuple(row.values()))
        self._conn.commit()
        return tx

    def get(self, ledger_id: str) -> Transaction | None:
        cur = self._conn.execute(
            "SELECT * FROM transactions WHERE ledger_id = ?", (ledger_id,)
        )
        row = cur.fetchone()
        return Transaction.from_row(row) if row else None

    def delete(self, ledger_id: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM transactions WHERE ledger_id = ?", (ledger_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def find_by_slip_hash(self, slip_hash: str) -> Transaction | None:
        if not slip_hash:
            return None
        cur = self._conn.execute(
            "SELECT * FROM transactions WHERE slip_hash = ? ORDER BY created_at DESC LIMIT 1",
            (slip_hash,),
        )
        row = cur.fetchone()
        return Transaction.from_row(row) if row else None

    def list_recent(self, limit: int = 20) -> list[Transaction]:
        cur = self._conn.execute(
            "SELECT * FROM transactions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [Transaction.from_row(r) for r in cur.fetchall()]

    def count_by_status(self, status: str) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) AS c FROM transactions WHERE status = ?", (status,)
        )
        return int(cur.fetchone()["c"])

    def count_open(self) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) AS c FROM transactions WHERE status != 'SETTLED' "
            "AND status != 'VOID'"
        )
        return int(cur.fetchone()["c"])

    def count_settled_today(self) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) AS c FROM transactions "
            "WHERE status = 'SETTLED' AND date(settled_at) = date('now')"
        )
        return int(cur.fetchone()["c"])

    def receiver_history(self, bank: str, last4: str) -> ReceiverHistory | None:
        cur = self._conn.execute(
            """
            SELECT
                bank,
                last4,
                MAX(receiver_name) AS receiver_name,
                COUNT(*) AS tx_count,
                COALESCE(SUM(thb), 0) AS total_thb,
                COALESCE(SUM(usdt), 0) AS total_usdt,
                MIN(created_at) AS first_seen,
                MAX(created_at) AS last_seen
            FROM transactions
            WHERE bank = ? AND last4 = ? AND status != 'VOID'
            GROUP BY bank, last4
            """,
            (bank, last4),
        )
        row = cur.fetchone()
        if not row or row["tx_count"] == 0:
            return None
        risk = _risk_from_count(int(row["tx_count"]))
        return ReceiverHistory(
            bank=row["bank"],
            last4=row["last4"],
            receiver_name=row["receiver_name"] or "",
            tx_count=int(row["tx_count"]),
            total_thb=float(row["total_thb"]),
            total_usdt=float(row["total_usdt"]),
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
            risk=risk,
        )

    def receiver_tx_count(self, bank: str, last4: str) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) AS c FROM transactions "
            "WHERE bank = ? AND last4 = ? AND status != 'VOID'",
            (bank, last4),
        )
        return int(cur.fetchone()["c"])

    def get_balance(self) -> float:
        cur = self._conn.execute("SELECT usdt_balance FROM balance WHERE id = 1")
        return float(cur.fetchone()["usdt_balance"])

    def add_balance(self, usdt_delta: float) -> float:
        new_bal = self.get_balance() + usdt_delta
        self._conn.execute(
            "UPDATE balance SET usdt_balance = ?, updated_at = ? WHERE id = 1",
            (new_bal, iso()),
        )
        self._conn.commit()
        return new_bal

    def set_setting(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        cur = self._conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
        return row["value"] if row else default


def _risk_from_count(count: int) -> str:
    if count >= 40:
        return "HIGH"
    if count >= 15:
        return "MED"
    return "LOW"
