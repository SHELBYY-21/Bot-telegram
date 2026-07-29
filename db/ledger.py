"""Ledger and receiver persistence."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from db.schema import init_db


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_ledger_id() -> str:
    return f"LV-{uuid.uuid4().hex[:8].upper()}"


@dataclass
class ReceiverHistory:
    bank: str
    last4: str
    receiver_name: str | None
    tx_count: int
    total_thb: float
    total_usdt: float
    first_seen: str
    last_seen: str
    risk_level: str

    @property
    def masked(self) -> str:
        return f"{self.bank} ••••{self.last4}"


@dataclass
class LedgerEntry:
    id: str
    slip_hash: str | None
    receiver: str | None
    bank: str | None
    last4: str | None
    thb: float
    usdt: float
    buy_rate: float
    sell_rate: float
    profit_pct: float
    staff: str
    status: str
    ocr_confidence: float | None
    ocr_payload: dict[str, Any] | None
    image_path: str | None
    created_at: str
    settled_at: str | None

    @property
    def masked_receiver(self) -> str | None:
        if self.bank and self.last4:
            return f"{self.bank} ••••{self.last4}"
        return self.receiver


class LedgerStore:
    def __init__(self, path: Path):
        self.path = path
        init_db(path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def slip_exists(self, slip_hash: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT ledger_id FROM slip_index WHERE slip_hash = ?",
                (slip_hash,),
            ).fetchone()
        return row["ledger_id"] if row else None

    def get_receiver(self, bank: str, last4: str) -> ReceiverHistory | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM receivers WHERE bank = ? AND last4 = ?",
                (bank, last4),
            ).fetchone()
        if not row:
            return None
        return ReceiverHistory(**dict(row))

    def upsert_receiver(
        self,
        bank: str,
        last4: str,
        receiver_name: str | None,
        thb: float,
        usdt: float,
    ) -> ReceiverHistory:
        now = utc_now()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM receivers WHERE bank = ? AND last4 = ?",
                (bank, last4),
            ).fetchone()
            if existing:
                tx_count = existing["tx_count"] + 1
                total_thb = existing["total_thb"] + thb
                total_usdt = existing["total_usdt"] + usdt
                first_seen = existing["first_seen"]
                risk = self._risk_level(tx_count, total_thb)
                conn.execute(
                    """
                    UPDATE receivers
                    SET receiver_name = COALESCE(?, receiver_name),
                        tx_count = ?, total_thb = ?, total_usdt = ?,
                        last_seen = ?, risk_level = ?
                    WHERE bank = ? AND last4 = ?
                    """,
                    (
                        receiver_name,
                        tx_count,
                        total_thb,
                        total_usdt,
                        now,
                        risk,
                        bank,
                        last4,
                    ),
                )
            else:
                tx_count = 1
                total_thb = thb
                total_usdt = usdt
                first_seen = now
                risk = "LOW"
                conn.execute(
                    """
                    INSERT INTO receivers (
                        bank, last4, receiver_name, tx_count, total_thb, total_usdt,
                        first_seen, last_seen, risk_level
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        bank,
                        last4,
                        receiver_name,
                        tx_count,
                        total_thb,
                        total_usdt,
                        first_seen,
                        now,
                        risk,
                    ),
                )
            conn.commit()
        return ReceiverHistory(
            bank=bank,
            last4=last4,
            receiver_name=receiver_name,
            tx_count=tx_count,
            total_thb=total_thb,
            total_usdt=total_usdt,
            first_seen=first_seen,
            last_seen=now,
            risk_level=risk,
        )

    @staticmethod
    def _risk_level(tx_count: int, total_thb: float) -> str:
        if tx_count >= 100 or total_thb >= 5_000_000:
            return "HIGH"
        if tx_count >= 25 or total_thb >= 1_000_000:
            return "MEDIUM"
        return "LOW"

    def create_entry(
        self,
        *,
        slip_hash: str | None,
        receiver: str | None,
        bank: str | None,
        last4: str | None,
        thb: float,
        usdt: float,
        buy_rate: float,
        sell_rate: float,
        profit_pct: float,
        staff: str,
        status: str,
        ocr_confidence: float | None = None,
        ocr_payload: dict[str, Any] | None = None,
        image_path: str | None = None,
    ) -> LedgerEntry:
        entry_id = new_ledger_id()
        now = utc_now()
        payload = json.dumps(ocr_payload) if ocr_payload else None
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ledger (
                    id, slip_hash, receiver, bank, last4, thb, usdt,
                    buy_rate, sell_rate, profit_pct, staff, status,
                    ocr_confidence, ocr_payload, image_path, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    slip_hash,
                    receiver,
                    bank,
                    last4,
                    thb,
                    usdt,
                    buy_rate,
                    sell_rate,
                    profit_pct,
                    staff,
                    status,
                    ocr_confidence,
                    payload,
                    image_path,
                    now,
                ),
            )
            if slip_hash:
                conn.execute(
                    "INSERT INTO slip_index (slip_hash, ledger_id, created_at) VALUES (?, ?, ?)",
                    (slip_hash, entry_id, now),
                )
            conn.commit()
        return self.get_entry(entry_id)

    def get_entry(self, entry_id: str) -> LedgerEntry:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM ledger WHERE id = ?", (entry_id,)).fetchone()
        if not row:
            raise KeyError(entry_id)
        return self._row_to_entry(row)

    def update_entry(
        self,
        entry_id: str,
        *,
        thb: float | None = None,
        usdt: float | None = None,
        buy_rate: float | None = None,
        sell_rate: float | None = None,
        profit_pct: float | None = None,
        status: str | None = None,
        receiver: str | None = None,
        bank: str | None = None,
        last4: str | None = None,
    ) -> LedgerEntry:
        entry = self.get_entry(entry_id)
        fields = {
            "thb": thb if thb is not None else entry.thb,
            "usdt": usdt if usdt is not None else entry.usdt,
            "buy_rate": buy_rate if buy_rate is not None else entry.buy_rate,
            "sell_rate": sell_rate if sell_rate is not None else entry.sell_rate,
            "profit_pct": profit_pct if profit_pct is not None else entry.profit_pct,
            "status": status if status is not None else entry.status,
            "receiver": receiver if receiver is not None else entry.receiver,
            "bank": bank if bank is not None else entry.bank,
            "last4": last4 if last4 is not None else entry.last4,
        }
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE ledger
                SET thb = ?, usdt = ?, buy_rate = ?, sell_rate = ?, profit_pct = ?,
                    status = ?, receiver = ?, bank = ?, last4 = ?
                WHERE id = ?
                """,
                (
                    fields["thb"],
                    fields["usdt"],
                    fields["buy_rate"],
                    fields["sell_rate"],
                    fields["profit_pct"],
                    fields["status"],
                    fields["receiver"],
                    fields["bank"],
                    fields["last4"],
                    entry_id,
                ),
            )
            conn.commit()
        return self.get_entry(entry_id)

    def settle_entry(self, entry_id: str) -> LedgerEntry:
        now = utc_now()
        entry = self.get_entry(entry_id)
        with self._connect() as conn:
            conn.execute(
                "UPDATE ledger SET status = ?, settled_at = ? WHERE id = ?",
                ("SETTLED", now, entry_id),
            )
            conn.commit()
        if entry.bank and entry.last4:
            self.upsert_receiver(
                entry.bank,
                entry.last4,
                entry.receiver,
                entry.thb,
                entry.usdt,
            )
        return self.get_entry(entry_id)

    def delete_entry(self, entry_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM slip_index WHERE ledger_id = ?", (entry_id,))
            conn.execute("DELETE FROM ledger WHERE id = ?", (entry_id,))
            conn.commit()

    def totals(self) -> dict[str, float]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(thb), 0) AS total_thb,
                    COALESCE(SUM(usdt), 0) AS total_usdt
                FROM ledger WHERE status = 'SETTLED'
                """
            ).fetchone()
        return {"total_thb": row["total_thb"], "total_usdt": row["total_usdt"]}

    def recent_entries(self, limit: int = 10) -> list[LedgerEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM ledger ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> LedgerEntry:
        payload = json.loads(row["ocr_payload"]) if row["ocr_payload"] else None
        return LedgerEntry(
            id=row["id"],
            slip_hash=row["slip_hash"],
            receiver=row["receiver"],
            bank=row["bank"],
            last4=row["last4"],
            thb=row["thb"],
            usdt=row["usdt"],
            buy_rate=row["buy_rate"],
            sell_rate=row["sell_rate"],
            profit_pct=row["profit_pct"],
            staff=row["staff"],
            status=row["status"],
            ocr_confidence=row["ocr_confidence"],
            ocr_payload=payload,
            image_path=row["image_path"],
            created_at=row["created_at"],
            settled_at=row["settled_at"],
        )

    def entry_to_dict(self, entry: LedgerEntry) -> dict[str, Any]:
        return asdict(entry)
