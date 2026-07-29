"""SQLite ledger — durable store for CE VAULT operations."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from ce_vault.design import LedgerStatus

DEFAULT_DB = Path(os.environ.get("LEDGER_DB", "data/ledger.db"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_ledger_id() -> str:
    return f"LV-{uuid.uuid4().hex[:10].upper()}"


class Ledger:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else DEFAULT_DB
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS entries (
                    ledger_id   TEXT PRIMARY KEY,
                    status      TEXT NOT NULL,
                    slip_hash   TEXT,
                    slip_file_id TEXT,
                    ocr_json    TEXT,
                    receiver    TEXT,
                    bank        TEXT,
                    last4       TEXT,
                    thb         REAL,
                    usdt        REAL,
                    buy_rate    REAL,
                    sell_rate   REAL,
                    profit      REAL,
                    confidence  REAL,
                    staff_id    INTEGER,
                    staff_name  TEXT,
                    chat_id     INTEGER,
                    message_id  INTEGER,
                    notes       TEXT,
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_entries_last4 ON entries(last4);
                CREATE INDEX IF NOT EXISTS idx_entries_slip_hash ON entries(slip_hash);
                CREATE INDEX IF NOT EXISTS idx_entries_status ON entries(status);
                CREATE INDEX IF NOT EXISTS idx_entries_created ON entries(created_at);

                CREATE TABLE IF NOT EXISTS events (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    ledger_id   TEXT NOT NULL,
                    event       TEXT NOT NULL,
                    payload     TEXT,
                    created_at  TEXT NOT NULL,
                    FOREIGN KEY (ledger_id) REFERENCES entries(ledger_id)
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    def create(
        self,
        *,
        staff_id: int | None = None,
        staff_name: str | None = None,
        chat_id: int | None = None,
        status: LedgerStatus = LedgerStatus.RECEIVED,
        **fields: Any,
    ) -> dict:
        ledger_id = fields.pop("ledger_id", None) or new_ledger_id()
        now = _utc_now()
        row = {
            "ledger_id": ledger_id,
            "status": status.value if isinstance(status, LedgerStatus) else status,
            "slip_hash": fields.get("slip_hash"),
            "slip_file_id": fields.get("slip_file_id"),
            "ocr_json": json.dumps(fields.get("ocr") or {}, ensure_ascii=False),
            "receiver": fields.get("receiver"),
            "bank": fields.get("bank"),
            "last4": fields.get("last4"),
            "thb": fields.get("thb"),
            "usdt": fields.get("usdt"),
            "buy_rate": fields.get("buy_rate"),
            "sell_rate": fields.get("sell_rate"),
            "profit": fields.get("profit"),
            "confidence": fields.get("confidence"),
            "staff_id": staff_id,
            "staff_name": staff_name,
            "chat_id": chat_id,
            "message_id": fields.get("message_id"),
            "notes": fields.get("notes"),
            "created_at": now,
            "updated_at": now,
        }
        cols = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        with self._conn() as conn:
            conn.execute(
                f"INSERT INTO entries ({cols}) VALUES ({placeholders})",
                tuple(row.values()),
            )
            conn.execute(
                "INSERT INTO events (ledger_id, event, payload, created_at) VALUES (?,?,?,?)",
                (ledger_id, "created", json.dumps(row, default=str), now),
            )
        return self.get(ledger_id)  # type: ignore[return-value]

    def get(self, ledger_id: str) -> dict | None:
        with self._conn() as conn:
            cur = conn.execute("SELECT * FROM entries WHERE ledger_id = ?", (ledger_id,))
            row = cur.fetchone()
            return self._row_to_dict(row) if row else None

    def update(self, ledger_id: str, **fields: Any) -> dict | None:
        allowed = {
            "status",
            "slip_hash",
            "slip_file_id",
            "ocr_json",
            "receiver",
            "bank",
            "last4",
            "thb",
            "usdt",
            "buy_rate",
            "sell_rate",
            "profit",
            "confidence",
            "message_id",
            "notes",
        }
        if "ocr" in fields:
            fields["ocr_json"] = json.dumps(fields.pop("ocr") or {}, ensure_ascii=False)
        if "status" in fields and isinstance(fields["status"], LedgerStatus):
            fields["status"] = fields["status"].value

        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return self.get(ledger_id)
        sets["updated_at"] = _utc_now()
        assignments = ", ".join(f"{k} = ?" for k in sets)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE entries SET {assignments} WHERE ledger_id = ?",
                (*sets.values(), ledger_id),
            )
            conn.execute(
                "INSERT INTO events (ledger_id, event, payload, created_at) VALUES (?,?,?,?)",
                (ledger_id, "updated", json.dumps(sets, default=str), sets["updated_at"]),
            )
        return self.get(ledger_id)

    def delete(self, ledger_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM events WHERE ledger_id = ?", (ledger_id,))
            cur = conn.execute("DELETE FROM entries WHERE ledger_id = ?", (ledger_id,))
            return cur.rowcount > 0

    def find_by_slip_hash(self, slip_hash: str) -> dict | None:
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT * FROM entries WHERE slip_hash = ? ORDER BY created_at DESC LIMIT 1",
                (slip_hash,),
            )
            row = cur.fetchone()
            return self._row_to_dict(row) if row else None

    def receiver_stats(self, last4: str, bank: str | None = None) -> dict:
        with self._conn() as conn:
            if bank:
                cur = conn.execute(
                    """
                    SELECT COUNT(*) AS tx_count,
                           COALESCE(SUM(thb),0) AS total_thb,
                           COALESCE(SUM(usdt),0) AS total_usdt,
                           MIN(created_at) AS first_seen,
                           MAX(created_at) AS last_seen,
                           MAX(receiver) AS receiver,
                           MAX(bank) AS bank
                    FROM entries
                    WHERE last4 = ? AND bank = ? AND status = ?
                    """,
                    (last4, bank, LedgerStatus.SETTLED.value),
                )
            else:
                cur = conn.execute(
                    """
                    SELECT COUNT(*) AS tx_count,
                           COALESCE(SUM(thb),0) AS total_thb,
                           COALESCE(SUM(usdt),0) AS total_usdt,
                           MIN(created_at) AS first_seen,
                           MAX(created_at) AS last_seen,
                           MAX(receiver) AS receiver,
                           MAX(bank) AS bank
                    FROM entries
                    WHERE last4 = ? AND status = ?
                    """,
                    (last4, LedgerStatus.SETTLED.value),
                )
            row = cur.fetchone()
            data = dict(row) if row else {}
            # Also count all statuses for volume awareness
            cur2 = conn.execute(
                "SELECT COUNT(*) FROM entries WHERE last4 = ?",
                (last4,),
            )
            all_count = cur2.fetchone()[0]
            if all_count and not data.get("tx_count"):
                cur3 = conn.execute(
                    """
                    SELECT COUNT(*) AS tx_count,
                           COALESCE(SUM(thb),0) AS total_thb,
                           COALESCE(SUM(usdt),0) AS total_usdt,
                           MIN(created_at) AS first_seen,
                           MAX(created_at) AS last_seen,
                           MAX(receiver) AS receiver,
                           MAX(bank) AS bank
                    FROM entries WHERE last4 = ?
                    """,
                    (last4,),
                )
                data = dict(cur3.fetchone())
            return data

    def receiver_seen_count(self, last4: str) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM entries WHERE last4 = ?",
                (last4,),
            )
            return int(cur.fetchone()[0])

    def settled_balance(self) -> dict[str, float]:
        with self._conn() as conn:
            cur = conn.execute(
                """
                SELECT COALESCE(SUM(thb),0), COALESCE(SUM(usdt),0)
                FROM entries WHERE status = ?
                """,
                (LedgerStatus.SETTLED.value,),
            )
            thb, usdt = cur.fetchone()
            return {"thb": float(thb), "usdt": float(usdt)}

    def recent(self, limit: int = 10) -> list[dict]:
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT * FROM entries ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
            return [self._row_to_dict(r) for r in cur.fetchall()]

    def risk_for(self, last4: str) -> str:
        count = self.receiver_seen_count(last4)
        if count >= 40:
            return "HIGH"
        if count >= 15:
            return "MED"
        return "LOW"

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        data = dict(row)
        try:
            data["ocr"] = json.loads(data.get("ocr_json") or "{}")
        except json.JSONDecodeError:
            data["ocr"] = {}
        return data
