"""Domain models for CE VAULT ledger operations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class OCRResult:
    receiver_name: str = ""
    bank: str = ""
    last4: str = ""
    amount_thb: float = 0.0
    confidence: float = 0.0
    slip_ref: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    verified: bool = False
    duplicate: bool = False
    warning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OCRResult:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class Transaction:
    ledger_id: str
    status: str
    thb: float = 0.0
    usdt: float = 0.0
    buy_rate: float = 0.0
    sell_rate: float = 0.0
    profit_pct: float = 0.0
    profit_thb: float = 0.0
    receiver_name: str = ""
    bank: str = ""
    last4: str = ""
    confidence: float = 0.0
    slip_hash: str = ""
    slip_ref: str = ""
    staff_id: int = 0
    staff_name: str = ""
    chat_id: int = 0
    message_id: int | None = None
    image_file_id: str = ""
    ocr_json: str = "{}"
    note: str = ""
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    settled_at: str = ""

    def receiver_mask(self) -> str:
        bank = self.bank or "BANK"
        last4 = self.last4 or "????"
        return f"{bank} ••••{last4}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReceiverHistory:
    bank: str
    last4: str
    receiver_name: str = ""
    tx_count: int = 0
    total_thb: float = 0.0
    total_usdt: float = 0.0
    first_seen: str = ""
    last_seen: str = ""
    risk: str = "LOW"

    def receiver_mask(self) -> str:
        return f"{self.bank} ••••{self.last4}"
