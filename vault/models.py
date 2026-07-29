"""Domain models for CE VAULT ledger operations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_ledger_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = uuid4().hex[:6].upper()
    return f"CV-{stamp}-{suffix}"


class TxStatus(str, Enum):
    RECEIVED = "RECEIVED"
    OCR_VERIFIED = "OCR VERIFIED"
    WAITING_USDT = "WAITING USDT"
    SETTLED = "SETTLED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


@dataclass
class OCRResult:
    receiver: str | None = None
    bank: str | None = None
    last4: str | None = None
    amount_thb: float | None = None
    confidence: float = 0.0
    raw_text: str = ""
    duplicate_slip: bool = False
    repeated_receiver: bool = False
    status: str = "Verified"

    @property
    def below_threshold(self) -> bool:
        return self.confidence < 90.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> OCRResult | None:
        if not data:
            return None
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Transaction:
    ledger_id: str
    status: str = TxStatus.RECEIVED.value
    thb: float | None = None
    usdt: float | None = None
    buy_rate: float | None = None
    sell_rate: float | None = None
    profit_pct: float | None = None
    receiver: str | None = None
    bank: str | None = None
    last4: str | None = None
    staff: str | None = None
    staff_id: int | None = None
    chat_id: int | None = None
    message_id: int | None = None
    slip_file_id: str | None = None
    slip_hash: str | None = None
    ocr_confidence: float | None = None
    ocr: dict[str, Any] | None = None
    notes: str | None = None
    created_at: str = field(default_factory=utcnow)
    updated_at: str = field(default_factory=utcnow)
    settled_at: str | None = None

    def touch(self) -> None:
        self.updated_at = utcnow()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def create(
        cls,
        *,
        staff: str | None = None,
        staff_id: int | None = None,
        chat_id: int | None = None,
    ) -> Transaction:
        return cls(
            ledger_id=new_ledger_id(),
            staff=staff,
            staff_id=staff_id,
            chat_id=chat_id,
        )


@dataclass
class ReceiverHistory:
    receiver: str
    bank: str | None
    last4: str | None
    tx_count: int
    total_thb: float
    total_usdt: float
    first_seen: str
    last_seen: str
    risk: str = "LOW"
