"""SQLite ledger — durable store for vault settlements."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_ledger_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"LED-{stamp}-{uuid.uuid4().hex[:6].upper()}"


@dataclass
class LedgerEntry:
    ledger_id: str
    status: str = "RECEIVED"
    thb: float | None = None
    usdt: float | None = None
    buy_rate: float | None = None
    sell_rate: float | None = None
    profit_pct: float | None = None
    profit_thb: float | None = None
    receiver_name: str | None = None
    bank: str | None = None
    last4: str | None = None
    ocr_confidence: float | None = None
    ocr_raw: dict | None = None
    slip_hash: str | None = None
    image_path: str | None = None
    staff_id: int | None = None
    staff_name: str | None = None
    notes: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)
    settled_at: str | None = None
    history: list[dict] = field(default_factory=list)

    def to_row(self) -> dict[str, Any]:
        data = asdict(self)
        data["ocr_raw"] = json.dumps(self.ocr_raw or {})
        data["history"] = json.dumps(self.history or [])
        return data


SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger (
    ledger_id      TEXT PRIMARY KEY,
    status         TEXT NOT NULL,
    thb            REAL,
    usdt           REAL,
    buy_rate       REAL,
    sell_rate      REAL,
    profit_pct     REAL,
    profit_thb     REAL,
    receiver_name  TEXT,
    bank           TEXT,
    last4          TEXT,
    ocr_confidence REAL,
    ocr_raw        TEXT,
    slip_hash      TEXT,
    image_path     TEXT,
    staff_id       INTEGER,
    staff_name     TEXT,
    notes          TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    settled_at     TEXT,
    history        TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_ledger_last4 ON ledger(last4);
CREATE INDEX IF NOT EXISTS idx_ledger_bank_last4 ON ledger(bank, last4);
CREATE INDEX IF NOT EXISTS idx_ledger_slip_hash ON ledger(slip_hash);
CREATE INDEX IF NOT EXISTS idx_ledger_created ON ledger(created_at);
CREATE INDEX IF NOT EXISTS idx_ledger_status ON ledger(status);

CREATE TABLE IF NOT EXISTS receivers (
    bank           TEXT NOT NULL,
    last4          TEXT NOT NULL,
    receiver_name  TEXT,
    tx_count       INTEGER NOT NULL DEFAULT 0,
    total_thb      REAL NOT NULL DEFAULT 0,
    total_usdt     REAL NOT NULL DEFAULT 0,
    first_seen     TEXT NOT NULL,
    last_seen      TEXT NOT NULL,
    PRIMARY KEY (bank, last4)
);
"""


class Ledger:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
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
        with self._tx() as conn:
            conn.executescript(SCHEMA)

    def _row_to_entry(self, row: sqlite3.Row) -> LedgerEntry:
        data = dict(row)
        data["ocr_raw"] = json.loads(data.get("ocr_raw") or "{}")
        data["history"] = json.loads(data.get("history") or "[]")
        return LedgerEntry(**data)

    def create(self, entry: LedgerEntry) -> LedgerEntry:
        entry.updated_at = _utcnow()
        if not entry.history:
            entry.history = [
                {"at": entry.created_at, "event": "created", "status": entry.status}
            ]
        with self._tx() as conn:
            cols = entry.to_row()
            placeholders = ", ".join("?" for _ in cols)
            columns = ", ".join(cols.keys())
            conn.execute(
                f"INSERT INTO ledger ({columns}) VALUES ({placeholders})",
                tuple(cols.values()),
            )
        return entry

    def get(self, ledger_id: str) -> LedgerEntry | None:
        with self._tx() as conn:
            row = conn.execute(
                "SELECT * FROM ledger WHERE ledger_id = ?", (ledger_id,)
            ).fetchone()
        return self._row_to_entry(row) if row else None

    def find_by_slip_hash(self, slip_hash: str) -> LedgerEntry | None:
        if not slip_hash:
            return None
        with self._tx() as conn:
            row = conn.execute(
                "SELECT * FROM ledger WHERE slip_hash = ? ORDER BY created_at DESC LIMIT 1",
                (slip_hash,),
            ).fetchone()
        return self._row_to_entry(row) if row else None

    def update(self, ledger_id: str, **fields: Any) -> LedgerEntry | None:
        entry = self.get(ledger_id)
        if not entry:
            return None
        event = fields.pop("event", "updated")
        for key, value in fields.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        entry.updated_at = _utcnow()
        entry.history = list(entry.history or [])
        entry.history.append(
            {
                "at": entry.updated_at,
                "event": event,
                "status": entry.status,
                "fields": sorted(fields.keys()),
            }
        )
        if entry.status == "SETTLED" and not entry.settled_at:
            entry.settled_at = entry.updated_at
        row = entry.to_row()
        assignments = ", ".join(f"{k} = ?" for k in row if k != "ledger_id")
        values = [v for k, v in row.items() if k != "ledger_id"]
        values.append(ledger_id)
        with self._tx() as conn:
            conn.execute(
                f"UPDATE ledger SET {assignments} WHERE ledger_id = ?",
                values,
            )
            if entry.status == "SETTLED" and entry.bank and entry.last4:
                self._upsert_receiver(conn, entry)
        return entry

    def delete(self, ledger_id: str) -> bool:
        with self._tx() as conn:
            cur = conn.execute("DELETE FROM ledger WHERE ledger_id = ?", (ledger_id,))
            return cur.rowcount > 0

    def recent(self, limit: int = 10) -> list[LedgerEntry]:
        with self._tx() as conn:
            rows = conn.execute(
                "SELECT * FROM ledger ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def receiver_history(self, bank: str, last4: str) -> dict[str, Any] | None:
        bank_n = (bank or "").strip().upper()
        last4_n = "".join(c for c in (last4 or "") if c.isdigit())[-4:]
        if not last4_n:
            return None
        with self._tx() as conn:
            row = conn.execute(
                "SELECT * FROM receivers WHERE bank = ? AND last4 = ?",
                (bank_n, last4_n),
            ).fetchone()
            if row:
                return dict(row)
            # Derive from ledger if receiver aggregate missing
            agg = conn.execute(
                """
                SELECT
                    COUNT(*) AS tx_count,
                    COALESCE(SUM(thb), 0) AS total_thb,
                    COALESCE(SUM(usdt), 0) AS total_usdt,
                    MIN(created_at) AS first_seen,
                    MAX(created_at) AS last_seen,
                    MAX(receiver_name) AS receiver_name
                FROM ledger
                WHERE UPPER(COALESCE(bank, '')) = ? AND last4 = ?
                """,
                (bank_n, last4_n),
            ).fetchone()
        if not agg or agg["tx_count"] == 0:
            return None
        return {
            "bank": bank_n,
            "last4": last4_n,
            "receiver_name": agg["receiver_name"],
            "tx_count": agg["tx_count"],
            "total_thb": agg["total_thb"],
            "total_usdt": agg["total_usdt"],
            "first_seen": agg["first_seen"],
            "last_seen": agg["last_seen"],
        }

    def count_receiver(self, bank: str, last4: str) -> int:
        hist = self.receiver_history(bank, last4)
        return int(hist["tx_count"]) if hist else 0

    def vault_balance(self) -> dict[str, float]:
        with self._tx() as conn:
            row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN status = 'SETTLED' THEN thb ELSE 0 END), 0) AS thb,
                    COALESCE(SUM(CASE WHEN status = 'SETTLED' THEN usdt ELSE 0 END), 0) AS usdt,
                    COALESCE(SUM(CASE WHEN status = 'SETTLED' THEN profit_thb ELSE 0 END), 0) AS profit
                FROM ledger
                """
            ).fetchone()
        return {
            "thb": float(row["thb"]),
            "usdt": float(row["usdt"]),
            "profit": float(row["profit"]),
        }

    @staticmethod
    def _upsert_receiver(conn: sqlite3.Connection, entry: LedgerEntry) -> None:
        bank = (entry.bank or "").strip().upper()
        last4 = "".join(c for c in (entry.last4 or "") if c.isdigit())[-4:]
        if not bank or not last4:
            return
        now = entry.settled_at or entry.updated_at
        existing = conn.execute(
            "SELECT * FROM receivers WHERE bank = ? AND last4 = ?",
            (bank, last4),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE receivers
                SET receiver_name = COALESCE(?, receiver_name),
                    tx_count = tx_count + 1,
                    total_thb = total_thb + ?,
                    total_usdt = total_usdt + ?,
                    last_seen = ?
                WHERE bank = ? AND last4 = ?
                """,
                (
                    entry.receiver_name,
                    float(entry.thb or 0),
                    float(entry.usdt or 0),
                    now,
                    bank,
                    last4,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO receivers (
                    bank, last4, receiver_name, tx_count, total_thb, total_usdt,
                    first_seen, last_seen
                ) VALUES (?, ?, ?, 1, ?, ?, ?, ?)
                """,
                (
                    bank,
                    last4,
                    entry.receiver_name,
                    float(entry.thb or 0),
                    float(entry.usdt or 0),
                    entry.created_at,
                    now,
                ),
            )


def slip_hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
