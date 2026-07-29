"""Data access layer for CE VAULT."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from config import DB_PATH, DEFAULT_BUY_RATE, DEFAULT_SELL_RATE
from db.schema import SCHEMA


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Repository:
    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                ("buy_rate", str(DEFAULT_BUY_RATE)),
            )
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                ("sell_rate", str(DEFAULT_SELL_RATE)),
            )

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --- settings ---

    def get_rate(self, key: str, default: float) -> float:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            return float(row["value"]) if row else default

    def set_rate(self, key: str, value: float) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, str(value)),
            )

    # --- receivers ---

    def upsert_receiver(
        self,
        bank: str,
        last4: str,
        name: str | None = None,
        thb: float = 0,
        usdt: float = 0,
    ) -> dict[str, Any]:
        now = _utcnow()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM receivers WHERE bank = ? AND last4 = ?",
                (bank, last4),
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE receivers SET
                        name = COALESCE(?, name),
                        last_seen = ?,
                        tx_count = tx_count + 1,
                        total_thb = total_thb + ?,
                        total_usdt = total_usdt + ?
                    WHERE id = ?""",
                    (name, now, thb, usdt, existing["id"]),
                )
                return dict(
                    conn.execute(
                        "SELECT * FROM receivers WHERE id = ?", (existing["id"],)
                    ).fetchone()
                )
            conn.execute(
                """INSERT INTO receivers
                    (bank, last4, name, first_seen, last_seen, tx_count, total_thb, total_usdt)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
                (bank, last4, name, now, now, thb, usdt),
            )
            rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            return dict(conn.execute("SELECT * FROM receivers WHERE id = ?", (rid,)).fetchone())

    def get_receiver(self, receiver_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM receivers WHERE id = ?", (receiver_id,)).fetchone()
            return dict(row) if row else None

    def find_receiver(self, bank: str, last4: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM receivers WHERE bank = ? AND last4 = ?",
                (bank, last4),
            ).fetchone()
            return dict(row) if row else None

    # --- transactions ---

    def create_transaction(
        self,
        ledger_id: str,
        staff_id: int,
        status: str,
        slip_hash: str | None = None,
        buy_rate: float | None = None,
        sell_rate: float | None = None,
        image_path: str | None = None,
    ) -> dict[str, Any]:
        now = _utcnow()
        buy = buy_rate or self.get_rate("buy_rate", DEFAULT_BUY_RATE)
        sell = sell_rate or self.get_rate("sell_rate", DEFAULT_SELL_RATE)
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO transactions
                    (id, slip_hash, staff_id, buy_rate, sell_rate, status, image_path, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (ledger_id, slip_hash, staff_id, buy, sell, status, image_path, now, now),
            )
            return self._get_tx_conn(conn, ledger_id)

    def update_transaction(self, ledger_id: str, **fields: Any) -> dict[str, Any] | None:
        if not fields:
            return self.get_transaction(ledger_id)
        fields["updated_at"] = _utcnow()
        if "ocr_data" in fields and isinstance(fields["ocr_data"], dict):
            fields["ocr_data"] = json.dumps(fields["ocr_data"])
        cols = ", ".join(f"{k} = ?" for k in fields)
        vals = list(fields.values()) + [ledger_id]
        with self._connect() as conn:
            conn.execute(f"UPDATE transactions SET {cols} WHERE id = ?", vals)
            return self._get_tx_conn(conn, ledger_id)

    def _get_tx_conn(self, conn: sqlite3.Connection, ledger_id: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM transactions WHERE id = ?", (ledger_id,)).fetchone()
        if not row:
            return None
        tx = dict(row)
        if tx.get("ocr_data"):
            try:
                tx["ocr_data"] = json.loads(tx["ocr_data"])
            except json.JSONDecodeError:
                pass
        return tx

    def get_transaction(self, ledger_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            return self._get_tx_conn(conn, ledger_id)

    def find_by_slip_hash(self, slip_hash: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM transactions WHERE slip_hash = ?", (slip_hash,)
            ).fetchone()
            if not row:
                return None
            tx = dict(row)
            if tx.get("ocr_data"):
                try:
                    tx["ocr_data"] = json.loads(tx["ocr_data"])
                except json.JSONDecodeError:
                    pass
            return tx

    def list_transactions(
        self, staff_id: int | None = None, limit: int = 20, status: str | None = None
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM transactions WHERE 1=1"
        params: list[Any] = []
        if staff_id is not None:
            query += " AND staff_id = ?"
            params.append(staff_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            result = []
            for row in rows:
                tx = dict(row)
                if tx.get("ocr_data"):
                    try:
                        tx["ocr_data"] = json.loads(tx["ocr_data"])
                    except json.JSONDecodeError:
                        pass
                result.append(tx)
            return result

    def get_pending_for_staff(self, staff_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT * FROM transactions
                WHERE staff_id = ? AND status NOT IN ('SETTLED', 'CANCELLED')
                ORDER BY created_at DESC LIMIT 1""",
                (staff_id,),
            ).fetchone()
            if not row:
                return None
            tx = dict(row)
            if tx.get("ocr_data"):
                try:
                    tx["ocr_data"] = json.loads(tx["ocr_data"])
                except json.JSONDecodeError:
                    pass
            return tx

    # --- balances ---

    def get_balance(self, staff_id: int) -> float:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT usdt_balance FROM balances WHERE staff_id = ?", (staff_id,)
            ).fetchone()
            return float(row["usdt_balance"]) if row else 0.0

    def adjust_balance(self, staff_id: int, delta: float) -> float:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT usdt_balance FROM balances WHERE staff_id = ?", (staff_id,)
            ).fetchone()
            current = float(row["usdt_balance"]) if row else 0.0
            new_balance = current + delta
            conn.execute(
                "INSERT OR REPLACE INTO balances (staff_id, usdt_balance) VALUES (?, ?)",
                (staff_id, new_balance),
            )
            return new_balance


_repo: Repository | None = None


def get_repository(db_path: Path | str | None = None) -> Repository:
    global _repo
    if db_path is not None:
        return Repository(db_path)
    if _repo is None:
        _repo = Repository()
    return _repo
