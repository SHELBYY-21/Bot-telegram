"""Ledger domain models."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class LedgerEntry:
    ledger_id: str
    status: str
    thb: Decimal = Decimal("0")
    usdt: Decimal = Decimal("0")
    buy_rate: Decimal = Decimal("0")
    sell_rate: Decimal = Decimal("0")
    profit: Decimal = Decimal("0")
    receiver: str = ""
    bank: str = ""
    last4: str = ""
    confidence: Decimal | None = None
    staff: str = ""
    staff_id: int | None = None
    chat_id: int | None = None
    message_id: int | None = None
    slip_hash: str | None = None
    slip_file_id: str | None = None
    ocr_raw: str | None = None
    images: list[str] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=utcnow)
    updated_at: str = field(default_factory=utcnow)
    settled_at: str | None = None

    def to_row(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("thb", "usdt", "buy_rate", "sell_rate", "profit", "confidence"):
            if data[key] is not None:
                data[key] = str(data[key])
        return data

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "LedgerEntry":
        def d(key: str, default: str = "0") -> Decimal:
            val = row.get(key)
            if val is None or val == "":
                return Decimal(default)
            return Decimal(str(val))

        images = row.get("images") or []
        history = row.get("history") or []
        if isinstance(images, str):
            images = json.loads(images)
        if isinstance(history, str):
            history = json.loads(history)

        conf = row.get("confidence")
        return cls(
            ledger_id=row["ledger_id"],
            status=row.get("status") or "RECEIVED",
            thb=d("thb"),
            usdt=d("usdt"),
            buy_rate=d("buy_rate"),
            sell_rate=d("sell_rate"),
            profit=d("profit"),
            receiver=row.get("receiver") or "",
            bank=row.get("bank") or "",
            last4=row.get("last4") or "",
            confidence=Decimal(str(conf)) if conf is not None and conf != "" else None,
            staff=row.get("staff") or "",
            staff_id=row.get("staff_id"),
            chat_id=row.get("chat_id"),
            message_id=row.get("message_id"),
            slip_hash=row.get("slip_hash"),
            slip_file_id=row.get("slip_file_id"),
            ocr_raw=row.get("ocr_raw"),
            images=list(images),
            history=list(history),
            created_at=row.get("created_at") or utcnow(),
            updated_at=row.get("updated_at") or utcnow(),
            settled_at=row.get("settled_at"),
        )
