"""SQLite ledger — durable transaction store with receiver history."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from vault.models import LedgerRecord, PipelineStatus, ReceiverHistory, RiskLevel

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ledger_id TEXT NOT NULL UNIQUE,
    slip_hash TEXT,
    slip_file_id TEXT,
    receiver_name TEXT NOT NULL DEFAULT '',
    bank TEXT NOT NULL DEFAULT '',
    last4 TEXT NOT NULL DEFAULT '',
    thb TEXT NOT NULL,
    usdt TEXT NOT NULL,
    buy_rate TEXT NOT NULL,
    sell_rate TEXT NOT NULL,
    profit_pct TEXT NOT NULL,
    ocr_confidence REAL,
    staff_id INTEGER,
    status TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'slip',
    created_at TEXT NOT NULL,
    settled_at TEXT,
    balance_thb TEXT,
    balance_usdt TEXT
);

CREATE INDEX IF NOT EXISTS idx_transactions_slip_hash ON transactions(slip_hash);
CREATE INDEX IF NOT EXISTS idx_transactions_receiver ON transactions(bank, last4);
CREATE INDEX IF NOT EXISTS idx_transactions_created ON transactions(created_at);
"""


class LedgerStore:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or Path(
            os.environ.get("LEDGER_DB", "storage/ledger.db")
        )
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def next_ledger_id(self) -> str:
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        prefix = f"LDG-{today}-"
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM transactions WHERE ledger_id LIKE ?",
                (f"{prefix}%",),
            ).fetchone()
            seq = int(row["c"]) + 1
        return f"{prefix}{seq:04d}"

    def slip_exists(self, slip_hash: str) -> bool:
        if not slip_hash:
            return False
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM transactions WHERE slip_hash = ? LIMIT 1",
                (slip_hash,),
            ).fetchone()
        return row is not None

    def get(self, ledger_id: str) -> LedgerRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM transactions WHERE ledger_id = ?",
                (ledger_id,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def insert_settled(self, record: dict) -> LedgerRecord:
        now = datetime.now(timezone.utc).isoformat()
        balances = self.totals()
        balance_thb = balances["thb"] + Decimal(record["thb"])
        balance_usdt = balances["usdt"] + Decimal(record["usdt"])

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO transactions (
                    ledger_id, slip_hash, slip_file_id, receiver_name, bank, last4,
                    thb, usdt, buy_rate, sell_rate, profit_pct, ocr_confidence,
                    staff_id, status, source, created_at, settled_at,
                    balance_thb, balance_usdt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["ledger_id"],
                    record.get("slip_hash"),
                    record.get("slip_file_id"),
                    record.get("receiver_name", ""),
                    record.get("bank", ""),
                    record.get("last4", ""),
                    record["thb"],
                    record["usdt"],
                    record["buy_rate"],
                    record["sell_rate"],
                    record["profit_pct"],
                    record.get("ocr_confidence"),
                    record.get("staff_id"),
                    PipelineStatus.SETTLED.value,
                    record.get("source", "slip"),
                    record.get("created_at", now),
                    now,
                    str(balance_thb),
                    str(balance_usdt),
                ),
            )
        saved = self.get(record["ledger_id"])
        assert saved is not None
        return saved

    def totals(self) -> dict[str, Decimal]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(CAST(thb AS REAL)), 0) AS thb,
                    COALESCE(SUM(CAST(usdt AS REAL)), 0) AS usdt,
                    COUNT(*) AS count
                FROM transactions
                WHERE status = ?
                """,
                (PipelineStatus.SETTLED.value,),
            ).fetchone()
        return {
            "thb": Decimal(str(row["thb"])).quantize(Decimal("0.01")),
            "usdt": Decimal(str(row["usdt"])).quantize(Decimal("0.0001")),
            "count": int(row["count"]),
        }

    def receiver_history(self, bank: str, last4: str) -> ReceiverHistory | None:
        if not bank or not last4:
            return None
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM transactions
                WHERE bank = ? AND last4 = ? AND status = ?
                ORDER BY created_at ASC
                """,
                (bank, last4, PipelineStatus.SETTLED.value),
            ).fetchall()
        if not rows:
            return None

        total_thb = sum(Decimal(r["thb"]) for r in rows)
        total_usdt = sum(Decimal(r["usdt"]) for r in rows)
        first_seen = rows[0]["created_at"][:10]
        last_seen = rows[-1]["created_at"][:10]
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if last_seen == today:
            last_seen = "Today"

        risk = RiskLevel.LOW
        if len(rows) >= 20:
            risk = RiskLevel.MEDIUM
        if len(rows) >= 50:
            risk = RiskLevel.HIGH

        return ReceiverHistory(
            receiver_name=rows[-1]["receiver_name"] or "Unknown",
            bank=bank,
            last4=last4,
            transaction_count=len(rows),
            total_thb=total_thb.quantize(Decimal("0.01")),
            total_usdt=total_usdt.quantize(Decimal("0.0001")),
            first_seen=first_seen,
            last_seen=last_seen,
            risk=risk,
        )

    def recent(self, limit: int = 5) -> list[LedgerRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM transactions
                WHERE status = ?
                ORDER BY settled_at DESC
                LIMIT ?
                """,
                (PipelineStatus.SETTLED.value, limit),
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def delete(self, ledger_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM transactions WHERE ledger_id = ?",
                (ledger_id,),
            )
        return cur.rowcount > 0

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> LedgerRecord:
        return LedgerRecord(
            ledger_id=row["ledger_id"],
            thb=Decimal(row["thb"]),
            usdt=Decimal(row["usdt"]),
            buy_rate=Decimal(row["buy_rate"]),
            sell_rate=Decimal(row["sell_rate"]),
            profit_pct=Decimal(row["profit_pct"]),
            receiver_name=row["receiver_name"],
            bank=row["bank"],
            last4=row["last4"],
            ocr_confidence=row["ocr_confidence"],
            staff_id=row["staff_id"],
            status=row["status"],
            slip_hash=row["slip_hash"],
            slip_file_id=row["slip_file_id"],
            source=row["source"],
            created_at=row["created_at"],
            settled_at=row["settled_at"],
            balance_thb=Decimal(row["balance_thb"]) if row["balance_thb"] else None,
            balance_usdt=Decimal(row["balance_usdt"]) if row["balance_usdt"] else None,
        )
