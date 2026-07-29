"""Domain models for CE VAULT ledger operations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    d = dt or utcnow()
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class OCRResult:
    receiver_name: str = ""
    bank: str = ""
    last4: str = ""
    amount_thb: float | None = None
    confidence: float = 0.0
    raw_text: str = ""
    verified: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> OCRResult:
        if not data:
            return cls()
        return cls(
            receiver_name=str(data.get("receiver_name") or ""),
            bank=str(data.get("bank") or ""),
            last4=str(data.get("last4") or ""),
            amount_thb=_float_or_none(data.get("amount_thb")),
            confidence=float(data.get("confidence") or 0.0),
            raw_text=str(data.get("raw_text") or ""),
            verified=bool(data.get("verified")),
            warnings=list(data.get("warnings") or []),
        )


@dataclass
class Transaction:
    ledger_id: str
    status: str
    thb: float | None = None
    usdt: float | None = None
    buy_rate: float | None = None
    sell_rate: float | None = None
    profit_pct: float | None = None
    receiver_name: str = ""
    bank: str = ""
    last4: str = ""
    confidence: float | None = None
    staff: str = ""
    staff_id: int | None = None
    chat_id: int | None = None
    message_id: int | None = None
    image_path: str | None = None
    slip_hash: str | None = None
    ocr_json: str | None = None
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""
    settled_at: str | None = None

    def receiver_mask(self) -> str:
        bank = self.bank or "BANK"
        last4 = self.last4 or "————"
        return f"{bank} ••••{last4}"

    def to_row(self) -> dict[str, Any]:
        return {
            "ledger_id": self.ledger_id,
            "status": self.status,
            "thb": self.thb,
            "usdt": self.usdt,
            "buy_rate": self.buy_rate,
            "sell_rate": self.sell_rate,
            "profit_pct": self.profit_pct,
            "receiver_name": self.receiver_name,
            "bank": self.bank,
            "last4": self.last4,
            "confidence": self.confidence,
            "staff": self.staff,
            "staff_id": self.staff_id,
            "chat_id": self.chat_id,
            "message_id": self.message_id,
            "image_path": self.image_path,
            "slip_hash": self.slip_hash,
            "ocr_json": self.ocr_json,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "settled_at": self.settled_at,
        }

    @classmethod
    def from_row(cls, row: Any) -> Transaction:
        data = dict(row)
        return cls(
            ledger_id=data["ledger_id"],
            status=data["status"],
            thb=data.get("thb"),
            usdt=data.get("usdt"),
            buy_rate=data.get("buy_rate"),
            sell_rate=data.get("sell_rate"),
            profit_pct=data.get("profit_pct"),
            receiver_name=data.get("receiver_name") or "",
            bank=data.get("bank") or "",
            last4=data.get("last4") or "",
            confidence=data.get("confidence"),
            staff=data.get("staff") or "",
            staff_id=data.get("staff_id"),
            chat_id=data.get("chat_id"),
            message_id=data.get("message_id"),
            image_path=data.get("image_path"),
            slip_hash=data.get("slip_hash"),
            ocr_json=data.get("ocr_json"),
            notes=data.get("notes") or "",
            created_at=data.get("created_at") or "",
            updated_at=data.get("updated_at") or "",
            settled_at=data.get("settled_at"),
        )


@dataclass
class ReceiverHistory:
    bank: str
    last4: str
    receiver_name: str
    tx_count: int
    total_thb: float
    total_usdt: float
    first_seen: str
    last_seen: str
    risk: str = "LOW"


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
