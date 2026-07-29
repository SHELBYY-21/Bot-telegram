"""Domain models for CE VAULT ledger operations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from ce_vault.theme import TxStatus


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_label(iso: str | None = None) -> str:
    """Human date; 'Today' when the calendar day matches UTC today."""
    if not iso:
        return "—"
    day = iso[:10]
    if day == datetime.now(timezone.utc).strftime("%Y-%m-%d"):
        return "Today"
    return day


@dataclass
class OCRResult:
    receiver_name: str = ""
    bank: str = ""
    last4: str = ""
    amount_thb: float = 0.0
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
            amount_thb=float(data.get("amount_thb") or 0),
            confidence=float(data.get("confidence") or 0),
            raw_text=str(data.get("raw_text") or ""),
            verified=bool(data.get("verified")),
            warnings=list(data.get("warnings") or []),
        )


@dataclass
class Transaction:
    ledger_id: str
    status: str = TxStatus.RECEIVED.value
    thb: float = 0.0
    usdt: float = 0.0
    buy_rate: float = 0.0
    sell_rate: float = 0.0
    profit_pct: float = 0.0
    receiver_name: str = ""
    bank: str = ""
    last4: str = ""
    confidence: float = 0.0
    slip_hash: str = ""
    ocr: dict[str, Any] = field(default_factory=dict)
    staff_id: int | None = None
    staff_name: str = ""
    chat_id: int | None = None
    image_file_id: str = ""
    notes: str = ""
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    settled_at: str | None = None
    deleted_at: str | None = None

    @property
    def receiver_display(self) -> str:
        bank = self.bank or "—"
        last4 = self.last4 or "····"
        return f"{bank} ••••{last4}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Transaction:
        import json

        ocr = row.get("ocr_json") or {}
        if isinstance(ocr, str):
            try:
                ocr = json.loads(ocr) if ocr else {}
            except json.JSONDecodeError:
                ocr = {}
        return cls(
            ledger_id=row["id"],
            status=row.get("status") or TxStatus.RECEIVED.value,
            thb=float(row.get("thb") or 0),
            usdt=float(row.get("usdt") or 0),
            buy_rate=float(row.get("buy_rate") or 0),
            sell_rate=float(row.get("sell_rate") or 0),
            profit_pct=float(row.get("profit_pct") or 0),
            receiver_name=row.get("receiver_name") or "",
            bank=row.get("bank") or "",
            last4=row.get("last4") or "",
            confidence=float(row.get("confidence") or 0),
            slip_hash=row.get("slip_hash") or "",
            ocr=ocr if isinstance(ocr, dict) else {},
            staff_id=row.get("staff_id"),
            staff_name=row.get("staff_name") or "",
            chat_id=row.get("chat_id"),
            image_file_id=row.get("image_file_id") or "",
            notes=row.get("notes") or "",
            created_at=row.get("created_at") or utc_now(),
            updated_at=row.get("updated_at") or utc_now(),
            settled_at=row.get("settled_at"),
            deleted_at=row.get("deleted_at"),
        )


@dataclass
class ReceiverProfile:
    bank: str
    last4: str
    name: str = ""
    tx_count: int = 0
    total_thb: float = 0.0
    total_usdt: float = 0.0
    first_seen: str = ""
    last_seen: str = ""
    risk: str = "LOW"

    @property
    def key(self) -> str:
        return f"{self.bank}:{self.last4}".upper()

    @property
    def display(self) -> str:
        return f"{self.bank} ••••{self.last4}"
