"""SQLite ledger — durable store for CE Vault settlements."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ledgers (
    id            TEXT PRIMARY KEY,
    status        TEXT NOT NULL,
    slip_file_id  TEXT,
    slip_hash     TEXT,
    ocr_json      TEXT,
    receiver_name TEXT,
    bank          TEXT,
    last4         TEXT,
    thb           TEXT,
    usdt          TEXT,
    buy_rate      TEXT,
    sell_rate     TEXT,
    profit_pct    TEXT,
    confidence    REAL,
    staff_id      INTEGER,
    staff_name    TEXT,
    chat_id       INTEGER,
    message_id    INTEGER,
    notes         TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    settled_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_ledgers_status ON ledgers(status);
CREATE INDEX IF NOT EXISTS idx_ledgers_last4 ON ledgers(bank, last4);
CREATE INDEX IF NOT EXISTS idx_ledgers_slip_hash ON ledgers(slip_hash);
CREATE INDEX IF NOT EXISTS idx_ledgers_created ON ledgers(created_at);

CREATE TABLE IF NOT EXISTS receivers (
    key           TEXT PRIMARY KEY,
    receiver_name TEXT,
    bank          TEXT,
    last4         TEXT,
    txn_count     INTEGER NOT NULL DEFAULT 0,
    total_thb     TEXT NOT NULL DEFAULT '0',
    total_usdt    TEXT NOT NULL DEFAULT '0',
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL,
    risk          TEXT NOT NULL DEFAULT 'LOW'
);

CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ledger_id  TEXT NOT NULL,
    kind       TEXT NOT NULL,
    payload    TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (ledger_id) REFERENCES ledgers(id)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_ledger_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"LED-{stamp}-{uuid.uuid4().hex[:6].upper()}"


def receiver_key(bank: str | None, last4: str | None, name: str | None = None) -> str:
    b = (bank or "").upper().strip()
    d = "".join(c for c in (last4 or "") if c.isdigit())[-4:]
    if b and d:
        return f"{b}:{d}"
    return f"name:{(name or '').strip().lower()}"


@dataclass
class LedgerRecord:
    id: str
    status: str
    slip_file_id: str | None
    slip_hash: str | None
    ocr_json: dict[str, Any] | None
    receiver_name: str | None
    bank: str | None
    last4: str | None
    thb: Decimal | None
    usdt: Decimal | None
    buy_rate: Decimal | None
    sell_rate: Decimal | None
    profit_pct: Decimal | None
    confidence: float | None
    staff_id: int | None
    staff_name: str | None
    chat_id: int | None
    message_id: int | None
    notes: str | None
    created_at: str
    updated_at: str
    settled_at: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "LedgerRecord":
        ocr = json.loads(row["ocr_json"]) if row["ocr_json"] else None

        def d(key: str) -> Decimal | None:
            v = row[key]
            return Decimal(v) if v is not None else None

        return cls(
            id=row["id"],
            status=row["status"],
            slip_file_id=row["slip_file_id"],
            slip_hash=row["slip_hash"],
            ocr_json=ocr,
            receiver_name=row["receiver_name"],
            bank=row["bank"],
            last4=row["last4"],
            thb=d("thb"),
            usdt=d("usdt"),
            buy_rate=d("buy_rate"),
            sell_rate=d("sell_rate"),
            profit_pct=d("profit_pct"),
            confidence=row["confidence"],
            staff_id=row["staff_id"],
            staff_name=row["staff_name"],
            chat_id=row["chat_id"],
            message_id=row["message_id"],
            notes=row["notes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            settled_at=row["settled_at"],
        )


@dataclass
class ReceiverStats:
    key: str
    receiver_name: str | None
    bank: str | None
    last4: str | None
    txn_count: int
    total_thb: Decimal
    total_usdt: Decimal
    first_seen: str
    last_seen: str
    risk: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ReceiverStats":
        return cls(
            key=row["key"],
            receiver_name=row["receiver_name"],
            bank=row["bank"],
            last4=row["last4"],
            txn_count=row["txn_count"],
            total_thb=Decimal(row["total_thb"] or "0"),
            total_usdt=Decimal(row["total_usdt"] or "0"),
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
            risk=row["risk"],
        )


class LedgerStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
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

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        with self._db() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        with self._db() as conn:
            conn.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def create(
        self,
        *,
        status: str = "RECEIVED",
        staff_id: int | None = None,
        staff_name: str | None = None,
        chat_id: int | None = None,
        slip_file_id: str | None = None,
        slip_hash: str | None = None,
        ledger_id: str | None = None,
    ) -> LedgerRecord:
        lid = ledger_id or new_ledger_id()
        now = _now()
        with self._db() as conn:
            conn.execute(
                """
                INSERT INTO ledgers (
                    id, status, slip_file_id, slip_hash, staff_id, staff_name,
                    chat_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (lid, status, slip_file_id, slip_hash, staff_id, staff_name, chat_id, now, now),
            )
            conn.execute(
                "INSERT INTO events(ledger_id, kind, payload, created_at) VALUES (?, ?, ?, ?)",
                (lid, "created", json.dumps({"status": status}), now),
            )
        record = self.get(lid)
        assert record
        return record

    def get(self, ledger_id: str) -> LedgerRecord | None:
        with self._db() as conn:
            row = conn.execute("SELECT * FROM ledgers WHERE id = ?", (ledger_id,)).fetchone()
            return LedgerRecord.from_row(row) if row else None

    def find_by_slip_hash(self, slip_hash: str) -> LedgerRecord | None:
        if not slip_hash:
            return None
        with self._db() as conn:
            row = conn.execute(
                "SELECT * FROM ledgers WHERE slip_hash = ? AND status != 'CANCELLED' ORDER BY created_at DESC LIMIT 1",
                (slip_hash,),
            ).fetchone()
            return LedgerRecord.from_row(row) if row else None

    def update(self, ledger_id: str, **fields: Any) -> LedgerRecord:
        allowed = {
            "status",
            "slip_file_id",
            "slip_hash",
            "ocr_json",
            "receiver_name",
            "bank",
            "last4",
            "thb",
            "usdt",
            "buy_rate",
            "sell_rate",
            "profit_pct",
            "confidence",
            "staff_id",
            "staff_name",
            "chat_id",
            "message_id",
            "notes",
            "settled_at",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            record = self.get(ledger_id)
            assert record
            return record

        if "ocr_json" in updates and updates["ocr_json"] is not None and not isinstance(updates["ocr_json"], str):
            updates["ocr_json"] = json.dumps(updates["ocr_json"], ensure_ascii=False)

        for money_key in ("thb", "usdt", "buy_rate", "sell_rate", "profit_pct"):
            if money_key in updates and updates[money_key] is not None:
                updates[money_key] = str(updates[money_key])

        updates["updated_at"] = _now()
        cols = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [ledger_id]
        with self._db() as conn:
            conn.execute(f"UPDATE ledgers SET {cols} WHERE id = ?", values)
            conn.execute(
                "INSERT INTO events(ledger_id, kind, payload, created_at) VALUES (?, ?, ?, ?)",
                (ledger_id, "update", json.dumps({k: str(v) for k, v in updates.items()}, ensure_ascii=False), updates["updated_at"]),
            )
        record = self.get(ledger_id)
        assert record
        return record

    def settle(self, ledger_id: str) -> LedgerRecord:
        record = self.update(ledger_id, status="SETTLED", settled_at=_now())
        self._bump_receiver(record)
        return record

    def cancel(self, ledger_id: str) -> LedgerRecord:
        return self.update(ledger_id, status="CANCELLED")

    def delete(self, ledger_id: str) -> bool:
        with self._db() as conn:
            cur = conn.execute("DELETE FROM events WHERE ledger_id = ?", (ledger_id,))
            cur = conn.execute("DELETE FROM ledgers WHERE id = ?", (ledger_id,))
            return cur.rowcount > 0

    def list_recent(self, *, limit: int = 10, status: str | None = None) -> list[LedgerRecord]:
        with self._db() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM ledgers WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM ledgers ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [LedgerRecord.from_row(r) for r in rows]

    def count_open(self) -> int:
        with self._db() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM ledgers WHERE status NOT IN ('SETTLED', 'CANCELLED', 'FAILED')"
            ).fetchone()
            return int(row["n"])

    def get_receiver(self, bank: str | None, last4: str | None, name: str | None = None) -> ReceiverStats | None:
        key = receiver_key(bank, last4, name)
        with self._db() as conn:
            row = conn.execute("SELECT * FROM receivers WHERE key = ?", (key,)).fetchone()
            return ReceiverStats.from_row(row) if row else None

    def receiver_history(self, bank: str | None, last4: str | None, name: str | None = None) -> ReceiverStats | None:
        return self.get_receiver(bank, last4, name)

    def risk_for(self, bank: str | None, last4: str | None, name: str | None = None) -> str:
        stats = self.get_receiver(bank, last4, name)
        if not stats:
            return "NEW"
        if stats.txn_count >= 40:
            return "WATCH"
        if stats.txn_count >= 10:
            return "LOW"
        return "LOW"

    def _bump_receiver(self, record: LedgerRecord) -> None:
        if not record.thb or not record.usdt:
            return
        key = receiver_key(record.bank, record.last4, record.receiver_name)
        now = _now()
        with self._db() as conn:
            existing = conn.execute("SELECT * FROM receivers WHERE key = ?", (key,)).fetchone()
            if existing:
                total_thb = Decimal(existing["total_thb"] or "0") + record.thb
                total_usdt = Decimal(existing["total_usdt"] or "0") + record.usdt
                count = existing["txn_count"] + 1
                risk = "WATCH" if count >= 40 else "LOW"
                conn.execute(
                    """
                    UPDATE receivers SET
                        receiver_name = ?,
                        bank = ?,
                        last4 = ?,
                        txn_count = ?,
                        total_thb = ?,
                        total_usdt = ?,
                        last_seen = ?,
                        risk = ?
                    WHERE key = ?
                    """,
                    (
                        record.receiver_name or existing["receiver_name"],
                        record.bank or existing["bank"],
                        record.last4 or existing["last4"],
                        count,
                        str(total_thb),
                        str(total_usdt),
                        now,
                        risk,
                        key,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO receivers (
                        key, receiver_name, bank, last4, txn_count,
                        total_thb, total_usdt, first_seen, last_seen, risk
                    ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, 'LOW')
                    """,
                    (
                        key,
                        record.receiver_name,
                        record.bank,
                        record.last4,
                        str(record.thb),
                        str(record.usdt),
                        now,
                        now,
                    ),
                )

    def balance_totals(self) -> tuple[Decimal, Decimal]:
        with self._db() as conn:
            row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(CAST(thb AS REAL)), 0) AS thb,
                    COALESCE(SUM(CAST(usdt AS REAL)), 0) AS usdt
                FROM ledgers WHERE status = 'SETTLED'
                """
            ).fetchone()
            return Decimal(str(row["thb"])), Decimal(str(row["usdt"]))
