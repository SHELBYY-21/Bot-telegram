"""Domain models for CE VAULT."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any


class PipelineStatus(str, Enum):
    RECEIVED = "RECEIVED"
    OCR_VERIFIED = "OCR VERIFIED"
    WAITING_USDT = "WAITING USDT"
    SETTLED = "SETTLED"

    @classmethod
    def ordered(cls) -> list[PipelineStatus]:
        return [cls.RECEIVED, cls.OCR_VERIFIED, cls.WAITING_USDT, cls.SETTLED]


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class OCRResult:
    receiver_name: str
    bank: str
    last4: str
    amount_thb: Decimal
    confidence: float
    raw_text: str = ""
    verified: bool = True

    @property
    def receiver_key(self) -> str:
        return f"{self.bank}|{self.last4}"


@dataclass
class ReceiverHistory:
    receiver_name: str
    bank: str
    last4: str
    transaction_count: int
    total_thb: Decimal
    total_usdt: Decimal
    first_seen: str
    last_seen: str
    risk: RiskLevel = RiskLevel.LOW

    @property
    def masked_account(self) -> str:
        return f"{self.bank} ••••{self.last4}"


@dataclass
class TransactionDraft:
    """In-progress transaction before settlement."""

    ledger_id: str
    thb: Decimal
    usdt: Decimal
    buy_rate: Decimal
    sell_rate: Decimal
    receiver_name: str = ""
    bank: str = ""
    last4: str = ""
    ocr_confidence: float | None = None
    slip_hash: str | None = None
    slip_file_id: str | None = None
    staff_id: int | None = None
    status: PipelineStatus = PipelineStatus.RECEIVED
    duplicate_slip: bool = False
    repeated_receiver: bool = False
    low_confidence: bool = False
    source: str = "slip"  # slip | usdt
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def profit_pct(self) -> Decimal:
        if self.buy_rate <= 0:
            return Decimal("0")
        spread = self.sell_rate - self.buy_rate
        return (spread / self.buy_rate * Decimal("100")).quantize(Decimal("0.01"))

    @property
    def masked_receiver(self) -> str:
        if self.bank and self.last4:
            return f"{self.bank} ••••{self.last4}"
        return "—"

    def to_record(self) -> dict[str, Any]:
        return {
            "ledger_id": self.ledger_id,
            "slip_hash": self.slip_hash,
            "slip_file_id": self.slip_file_id,
            "receiver_name": self.receiver_name,
            "bank": self.bank,
            "last4": self.last4,
            "thb": str(self.thb),
            "usdt": str(self.usdt),
            "buy_rate": str(self.buy_rate),
            "sell_rate": str(self.sell_rate),
            "profit_pct": str(self.profit_pct),
            "ocr_confidence": self.ocr_confidence,
            "staff_id": self.staff_id,
            "status": self.status.value,
            "source": self.source,
            "created_at": self.created_at,
        }


@dataclass
class LedgerRecord:
    ledger_id: str
    thb: Decimal
    usdt: Decimal
    buy_rate: Decimal
    sell_rate: Decimal
    profit_pct: Decimal
    receiver_name: str
    bank: str
    last4: str
    ocr_confidence: float | None
    staff_id: int | None
    status: str
    slip_hash: str | None
    slip_file_id: str | None
    source: str
    created_at: str
    settled_at: str | None = None
    balance_thb: Decimal | None = None
    balance_usdt: Decimal | None = None
