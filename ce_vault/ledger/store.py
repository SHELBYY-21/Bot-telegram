"""SQLite ledger store — optimized indexes for receiver history & duplicates."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from ce_vault.ledger.models import LedgerEntry, utcnow
from ce_vault.theme import mask_account, to_decimal

DEFAULT_DB = Path(os.environ.get("LEDGER_DB", "ledger.db"))


class LedgerStore:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or DEFAULT_DB)
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS ledger (
                        ledger_id     TEXT PRIMARY KEY,
                        status        TEXT NOT NULL,
                        thb           TEXT NOT NULL DEFAULT '0',
                        usdt          TEXT NOT NULL DEFAULT '0',
                        buy_rate      TEXT NOT NULL DEFAULT '0',
                        sell_rate     TEXT NOT NULL DEFAULT '0',
                        profit        TEXT NOT NULL DEFAULT '0',
                        receiver      TEXT NOT NULL DEFAULT '',
                        bank          TEXT NOT NULL DEFAULT '',
                        last4         TEXT NOT NULL DEFAULT '',
                        confidence    TEXT,
                        staff         TEXT NOT NULL DEFAULT '',
                        staff_id      INTEGER,
                        chat_id       INTEGER,
                        message_id    INTEGER,
                        slip_hash     TEXT,
                        slip_file_id  TEXT,
                        ocr_raw       TEXT,
                        images_json   TEXT NOT NULL DEFAULT '[]',
                        history_json  TEXT NOT NULL DEFAULT '[]',
                        created_at    TEXT NOT NULL,
                        updated_at    TEXT NOT NULL,
                        settled_at    TEXT
                    );

                    CREATE INDEX IF NOT EXISTS idx_ledger_status
                        ON ledger(status);
                    CREATE INDEX IF NOT EXISTS idx_ledger_receiver
                        ON ledger(bank, last4);
                    CREATE INDEX IF NOT EXISTS idx_ledger_slip_hash
                        ON ledger(slip_hash);
                    CREATE INDEX IF NOT EXISTS idx_ledger_created
                        ON ledger(created_at);
                    CREATE INDEX IF NOT EXISTS idx_ledger_chat
                        ON ledger(chat_id);

                    CREATE TABLE IF NOT EXISTS vault_meta (
                        key   TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    """
                )
                conn.commit()
                if self.get_meta("balance_usdt") is None:
                    self.set_meta("balance_usdt", os.environ.get("DEFAULT_BALANCE_USDT", "100000"))
                if self.get_meta("buy_rate") is None:
                    self.set_meta("buy_rate", os.environ.get("DEFAULT_BUY_RATE", "39.89"))
                if self.get_meta("sell_rate") is None:
                    self.set_meta("sell_rate", os.environ.get("DEFAULT_SELL_RATE", "40.00"))
            finally:
                conn.close()

    # --- meta / rates / balance -----------------------------------------

    def get_meta(self, key: str) -> str | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT value FROM vault_meta WHERE key = ?", (key,)
                ).fetchone()
                return None if row is None else str(row["value"])
            finally:
                conn.close()

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO vault_meta(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )
                conn.commit()
            finally:
                conn.close()

    def get_balance(self) -> Decimal:
        return to_decimal(self.get_meta("balance_usdt") or "0")

    def set_balance(self, value: Decimal) -> None:
        self.set_meta("balance_usdt", str(value))

    def adjust_balance(self, delta: Decimal) -> Decimal:
        with self._lock:
            bal = self.get_balance() + delta
            self.set_balance(bal)
            return bal

    def get_rates(self) -> tuple[Decimal, Decimal]:
        buy = to_decimal(self.get_meta("buy_rate") or "39.89")
        sell = to_decimal(self.get_meta("sell_rate") or "40.00")
        return buy, sell

    def set_rates(self, buy: Decimal, sell: Decimal) -> None:
        self.set_meta("buy_rate", str(buy))
        self.set_meta("sell_rate", str(sell))

    # --- id generation --------------------------------------------------

    @staticmethod
    def new_ledger_id() -> str:
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        suffix = uuid.uuid4().hex[:6].upper()
        return f"LDG-{day}-{suffix}"

    # --- CRUD -----------------------------------------------------------

    def upsert(self, entry: LedgerEntry) -> LedgerEntry:
        entry.updated_at = utcnow()
        row = entry.to_row()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO ledger (
                        ledger_id, status, thb, usdt, buy_rate, sell_rate, profit,
                        receiver, bank, last4, confidence, staff, staff_id,
                        chat_id, message_id, slip_hash, slip_file_id, ocr_raw,
                        images_json, history_json, created_at, updated_at, settled_at
                    ) VALUES (
                        :ledger_id, :status, :thb, :usdt, :buy_rate, :sell_rate, :profit,
                        :receiver, :bank, :last4, :confidence, :staff, :staff_id,
                        :chat_id, :message_id, :slip_hash, :slip_file_id, :ocr_raw,
                        :images_json, :history_json, :created_at, :updated_at, :settled_at
                    )
                    ON CONFLICT(ledger_id) DO UPDATE SET
                        status=excluded.status,
                        thb=excluded.thb,
                        usdt=excluded.usdt,
                        buy_rate=excluded.buy_rate,
                        sell_rate=excluded.sell_rate,
                        profit=excluded.profit,
                        receiver=excluded.receiver,
                        bank=excluded.bank,
                        last4=excluded.last4,
                        confidence=excluded.confidence,
                        staff=excluded.staff,
                        staff_id=excluded.staff_id,
                        chat_id=excluded.chat_id,
                        message_id=excluded.message_id,
                        slip_hash=excluded.slip_hash,
                        slip_file_id=excluded.slip_file_id,
                        ocr_raw=excluded.ocr_raw,
                        images_json=excluded.images_json,
                        history_json=excluded.history_json,
                        updated_at=excluded.updated_at,
                        settled_at=excluded.settled_at
                    """,
                    {
                        **row,
                        "images_json": json.dumps(row.get("images") or []),
                        "history_json": json.dumps(row.get("history") or []),
                    },
                )
                conn.commit()
            finally:
                conn.close()
        return entry

    def get(self, ledger_id: str) -> LedgerEntry | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM ledger WHERE ledger_id = ?", (ledger_id,)
                ).fetchone()
                return None if row is None else self._row_to_entry(row)
            finally:
                conn.close()

    def delete(self, ledger_id: str) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute("DELETE FROM ledger WHERE ledger_id = ?", (ledger_id,))
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def list_by_status(self, status: str, limit: int = 20) -> list[LedgerEntry]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM ledger WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
                return [self._row_to_entry(r) for r in rows]
            finally:
                conn.close()

    def count_by_status(self, status: str) -> int:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM ledger WHERE status = ?", (status,)
                ).fetchone()
                return int(row["c"])
            finally:
                conn.close()

    def count_settled_today(self) -> int:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM ledger "
                    "WHERE status = 'SETTLED' AND settled_at LIKE ?",
                    (f"{today}%",),
                ).fetchone()
                return int(row["c"])
            finally:
                conn.close()

    def find_by_slip_hash(self, slip_hash: str) -> LedgerEntry | None:
        if not slip_hash:
            return None
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM ledger WHERE slip_hash = ? ORDER BY created_at DESC LIMIT 1",
                    (slip_hash,),
                ).fetchone()
                return None if row is None else self._row_to_entry(row)
            finally:
                conn.close()

    def receiver_history(self, bank: str, last4: str) -> dict[str, Any]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM ledger WHERE bank = ? AND last4 = ? "
                    "AND status = 'SETTLED' ORDER BY created_at ASC",
                    (bank.upper(), last4),
                ).fetchall()
            finally:
                conn.close()

        entries = [self._row_to_entry(r) for r in rows]
        if not entries:
            return {
                "receiver_mask": mask_account(last4, bank),
                "tx_count": 0,
                "total_thb": Decimal("0"),
                "total_usdt": Decimal("0"),
                "first_seen": "—",
                "last_seen": "—",
                "risk": "NEW",
            }

        total_thb = sum((e.thb for e in entries), Decimal("0"))
        total_usdt = sum((e.usdt for e in entries), Decimal("0"))
        first = entries[0].created_at[:10]
        last_raw = entries[-1].settled_at or entries[-1].created_at
        last = _relative_day(last_raw)
        risk = _risk_level(len(entries), total_thb)

        return {
            "receiver_mask": mask_account(last4, bank),
            "tx_count": len(entries),
            "total_thb": total_thb,
            "total_usdt": total_usdt,
            "first_seen": first,
            "last_seen": last,
            "risk": risk,
        }

    def append_history(self, ledger_id: str, event: str, detail: dict[str, Any] | None = None) -> None:
        entry = self.get(ledger_id)
        if not entry:
            return
        entry.history.append(
            {"at": utcnow(), "event": event, "detail": detail or {}}
        )
        self.upsert(entry)

    def set_message(self, ledger_id: str, chat_id: int, message_id: int) -> None:
        entry = self.get(ledger_id)
        if not entry:
            return
        entry.chat_id = chat_id
        entry.message_id = message_id
        self.upsert(entry)

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> LedgerEntry:
        data = dict(row)
        data["images"] = json.loads(data.pop("images_json") or "[]")
        data["history"] = json.loads(data.pop("history_json") or "[]")
        return LedgerEntry.from_row(data)


def _relative_day(iso: str) -> str:
    day = iso[:10]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if day == today:
        return "Today"
    return day


def _risk_level(tx_count: int, total_thb: Decimal) -> str:
    if tx_count >= 40 or total_thb >= Decimal("2000000"):
        return "HIGH"
    if tx_count >= 15 or total_thb >= Decimal("500000"):
        return "MED"
    return "LOW"
