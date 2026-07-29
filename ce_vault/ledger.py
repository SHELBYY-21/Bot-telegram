"""SQLite ledger — durable store for CE VAULT operations."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from ce_vault.formatting import ledger_id as make_ledger_id
from ce_vault.theme import RECEIVER_REPEAT_HOURS, Status


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rates (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    buy_rate REAL NOT NULL,
    sell_rate REAL NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by INTEGER
);

CREATE TABLE IF NOT EXISTS ledger (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    slip_file_id TEXT,
    slip_hash TEXT,
    ocr_json TEXT,
    ocr_confidence REAL,
    receiver_name TEXT,
    bank TEXT,
    last4 TEXT,
    thb REAL,
    usdt REAL,
    buy_rate REAL,
    sell_rate REAL,
    profit_pct REAL,
    staff_id INTEGER,
    staff_name TEXT,
    chat_id INTEGER,
    message_id INTEGER,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    settled_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_ledger_status ON ledger(status);
CREATE INDEX IF NOT EXISTS idx_ledger_slip_hash ON ledger(slip_hash);
CREATE INDEX IF NOT EXISTS idx_ledger_receiver ON ledger(bank, last4);
CREATE INDEX IF NOT EXISTS idx_ledger_created ON ledger(created_at DESC);

CREATE TABLE IF NOT EXISTS receivers (
    key TEXT PRIMARY KEY,
    bank TEXT NOT NULL,
    last4 TEXT NOT NULL,
    name TEXT,
    tx_count INTEGER NOT NULL DEFAULT 0,
    total_thb REAL NOT NULL DEFAULT 0,
    total_usdt REAL NOT NULL DEFAULT 0,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    risk TEXT NOT NULL DEFAULT 'LOW'
);

CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ledger_id TEXT NOT NULL REFERENCES ledger(id) ON DELETE CASCADE,
    file_id TEXT NOT NULL,
    file_unique_id TEXT,
    created_at TEXT NOT NULL
);
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def receiver_key(bank: str | None, last4: str | None) -> str | None:
    if not bank or not last4:
        return None
    return f"{bank.upper().strip()}:{(last4 or '')[-4:]}"


class Ledger:
    """Thread-safe SQLite ledger with WAL mode."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
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
            row = conn.execute("SELECT buy_rate FROM rates WHERE id = 1").fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO rates (id, buy_rate, sell_rate, updated_at) VALUES (1, ?, ?, ?)",
                    (39.89, 40.00, _utcnow()),
                )
            bal = conn.execute("SELECT value FROM meta WHERE key = 'usdt_balance'").fetchone()
            if bal is None:
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('usdt_balance', ?)",
                    ("0"),
                )

    # --- rates / balance -------------------------------------------------

    def get_rates(self) -> tuple[float, float]:
        with self._db() as conn:
            row = conn.execute("SELECT buy_rate, sell_rate FROM rates WHERE id = 1").fetchone()
            return float(row["buy_rate"]), float(row["sell_rate"])

    def set_rates(self, buy: float, sell: float, updated_by: int | None = None) -> None:
        with self._db() as conn:
            conn.execute(
                """
                INSERT INTO rates (id, buy_rate, sell_rate, updated_at, updated_by)
                VALUES (1, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    buy_rate = excluded.buy_rate,
                    sell_rate = excluded.sell_rate,
                    updated_at = excluded.updated_at,
                    updated_by = excluded.updated_by
                """,
                (buy, sell, _utcnow(), updated_by),
            )

    def get_balance(self) -> float:
        with self._db() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = 'usdt_balance'").fetchone()
            return float(row["value"]) if row else 0.0

    def set_balance(self, value: float) -> None:
        with self._db() as conn:
            conn.execute(
                """
                INSERT INTO meta (key, value) VALUES ('usdt_balance', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(value),),
            )

    def adjust_balance(self, delta: float) -> float:
        with self._db() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = 'usdt_balance'").fetchone()
            current = float(row["value"]) if row else 0.0
            new = round(current + delta, 4)
            conn.execute(
                """
                INSERT INTO meta (key, value) VALUES ('usdt_balance', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(new),),
            )
            return new

    # --- ledger ids ------------------------------------------------------

    def next_ledger_id(self) -> str:
        with self._db() as conn:
            today = datetime.now(timezone.utc).strftime("%Y%m%d")
            prefix = f"LV-{today}-"
            row = conn.execute(
                "SELECT id FROM ledger WHERE id LIKE ? ORDER BY id DESC LIMIT 1",
                (prefix + "%",),
            ).fetchone()
            seq = 1
            if row:
                try:
                    seq = int(str(row["id"]).rsplit("-", 1)[-1]) + 1
                except ValueError:
                    seq = 1
            return make_ledger_id(seq=seq)

    # --- CRUD ------------------------------------------------------------

    def create_entry(self, **fields: Any) -> dict:
        entry_id = fields.pop("id", None) or self.next_ledger_id()
        now = _utcnow()
        payload = {
            "id": entry_id,
            "status": fields.get("status", Status.RECEIVED.value),
            "slip_file_id": fields.get("slip_file_id"),
            "slip_hash": fields.get("slip_hash"),
            "ocr_json": json.dumps(fields["ocr"]) if fields.get("ocr") is not None else fields.get("ocr_json"),
            "ocr_confidence": fields.get("ocr_confidence"),
            "receiver_name": fields.get("receiver_name"),
            "bank": fields.get("bank"),
            "last4": fields.get("last4"),
            "thb": fields.get("thb"),
            "usdt": fields.get("usdt"),
            "buy_rate": fields.get("buy_rate"),
            "sell_rate": fields.get("sell_rate"),
            "profit_pct": fields.get("profit_pct"),
            "staff_id": fields.get("staff_id"),
            "staff_name": fields.get("staff_name"),
            "chat_id": fields.get("chat_id"),
            "message_id": fields.get("message_id"),
            "notes": fields.get("notes"),
            "created_at": now,
            "updated_at": now,
            "settled_at": None,
        }
        cols = ", ".join(payload.keys())
        placeholders = ", ".join("?" for _ in payload)
        with self._db() as conn:
            conn.execute(
                f"INSERT INTO ledger ({cols}) VALUES ({placeholders})",
                tuple(payload.values()),
            )
            if payload.get("slip_file_id"):
                conn.execute(
                    "INSERT INTO images (ledger_id, file_id, created_at) VALUES (?, ?, ?)",
                    (entry_id, payload["slip_file_id"], now),
                )
        return self.get(entry_id)  # type: ignore[return-value]

    def get(self, entry_id: str) -> dict | None:
        with self._db() as conn:
            row = conn.execute("SELECT * FROM ledger WHERE id = ?", (entry_id,)).fetchone()
            return dict(row) if row else None

    def update(self, entry_id: str, **fields: Any) -> dict | None:
        if not fields:
            return self.get(entry_id)
        fields = dict(fields)
        if "ocr" in fields:
            fields["ocr_json"] = json.dumps(fields.pop("ocr"))
        fields["updated_at"] = _utcnow()
        assignments = ", ".join(f"{k} = ?" for k in fields)
        with self._db() as conn:
            conn.execute(
                f"UPDATE ledger SET {assignments} WHERE id = ?",
                (*fields.values(), entry_id),
            )
        return self.get(entry_id)

    def delete(self, entry_id: str) -> bool:
        with self._db() as conn:
            cur = conn.execute("DELETE FROM ledger WHERE id = ?", (entry_id,))
            return cur.rowcount > 0

    def list_recent(self, limit: int = 10) -> list[dict]:
        with self._db() as conn:
            rows = conn.execute(
                "SELECT * FROM ledger ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def find_by_slip_hash(self, slip_hash: str) -> dict | None:
        if not slip_hash:
            return None
        with self._db() as conn:
            row = conn.execute(
                "SELECT * FROM ledger WHERE slip_hash = ? AND status != ? ORDER BY created_at DESC LIMIT 1",
                (slip_hash, Status.CANCELLED.value),
            ).fetchone()
            return dict(row) if row else None

    # --- receivers -------------------------------------------------------

    def receiver_history(self, bank: str | None, last4: str | None) -> dict | None:
        key = receiver_key(bank, last4)
        if not key:
            return None
        with self._db() as conn:
            row = conn.execute("SELECT * FROM receivers WHERE key = ?", (key,)).fetchone()
            return dict(row) if row else None

    def is_repeat_receiver(self, bank: str | None, last4: str | None, hours: int = RECEIVER_REPEAT_HOURS) -> bool:
        key = receiver_key(bank, last4)
        if not key:
            return False
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self._db() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS n FROM ledger
                WHERE bank = ? AND last4 = ? AND created_at >= ? AND status != ?
                """,
                (bank, last4, cutoff, Status.CANCELLED.value),
            ).fetchone()
            return bool(row and row["n"] > 0)

    def record_settlement(self, entry_id: str) -> dict | None:
        entry = self.get(entry_id)
        if not entry:
            return None
        now = _utcnow()
        with self._db() as conn:
            conn.execute(
                """
                UPDATE ledger
                SET status = ?, settled_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (Status.SETTLED.value, now, now, entry_id),
            )
            # Debit USDT balance on settle
            usdt = float(entry["usdt"] or 0)
            row = conn.execute("SELECT value FROM meta WHERE key = 'usdt_balance'").fetchone()
            current = float(row["value"]) if row else 0.0
            new_bal = round(current - usdt, 4)
            conn.execute(
                """
                INSERT INTO meta (key, value) VALUES ('usdt_balance', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(new_bal),),
            )

            key = receiver_key(entry.get("bank"), entry.get("last4"))
            if key:
                existing = conn.execute(
                    "SELECT * FROM receivers WHERE key = ?", (key,)
                ).fetchone()
                thb = float(entry.get("thb") or 0)
                if existing:
                    risk = existing["risk"]
                    tx_count = int(existing["tx_count"]) + 1
                    if tx_count >= 20:
                        risk = "MED"
                    if tx_count >= 50:
                        risk = "HIGH"
                    conn.execute(
                        """
                        UPDATE receivers SET
                            name = COALESCE(?, name),
                            tx_count = tx_count + 1,
                            total_thb = total_thb + ?,
                            total_usdt = total_usdt + ?,
                            last_seen = ?,
                            risk = ?
                        WHERE key = ?
                        """,
                        (
                            entry.get("receiver_name"),
                            thb,
                            usdt,
                            now,
                            risk,
                            key,
                        ),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO receivers (
                            key, bank, last4, name, tx_count, total_thb, total_usdt,
                            first_seen, last_seen, risk
                        ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, 'LOW')
                        """,
                        (
                            key,
                            entry.get("bank") or "BANK",
                            entry.get("last4") or "0000",
                            entry.get("receiver_name"),
                            thb,
                            usdt,
                            now,
                            now,
                        ),
                    )
        return self.get(entry_id)
