"""Transaction orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from db.ledger import LedgerEntry, LedgerStore, ReceiverHistory
from services.ocr import OCRResult, OCRService
from services.rates import RateQuote, RateService


@dataclass
class PendingTransaction:
    ledger_id: str
    quote: RateQuote
    ocr: OCRResult | None
    receiver_history: ReceiverHistory | None
    slip_hash: str | None
    image_path: str | None
    status: str


class TransactionService:
    STATUSES = ("RECEIVED", "OCR_VERIFIED", "WAITING_USDT", "SETTLED")

    def __init__(
        self,
        store: LedgerStore,
        rates: RateService,
        ocr: OCRService,
        staff_name: str,
    ):
        self.store = store
        self.rates = rates
        self.ocr = ocr
        self.staff_name = staff_name

    def create_from_ocr(
        self,
        ocr: OCRResult,
        *,
        slip_hash: str | None = None,
        image_path: str | None = None,
        status: str = "OCR_VERIFIED",
    ) -> PendingTransaction:
        if not ocr.amount_thb:
            raise ValueError("OCR did not detect amount")
        quote = self.rates.from_thb(ocr.amount_thb)
        history = None
        if ocr.bank and ocr.last4:
            history = self.store.get_receiver(ocr.bank, ocr.last4)
        entry = self.store.create_entry(
            slip_hash=slip_hash,
            receiver=ocr.receiver_name,
            bank=ocr.bank,
            last4=ocr.last4,
            thb=quote.thb,
            usdt=quote.usdt,
            buy_rate=quote.buy_rate,
            sell_rate=quote.sell_rate,
            profit_pct=quote.profit_pct,
            staff=self.staff_name,
            status=status,
            ocr_confidence=ocr.confidence,
            ocr_payload={
                "receiver_name": ocr.receiver_name,
                "bank": ocr.bank,
                "last4": ocr.last4,
                "raw_text": ocr.raw_text,
                "verified": ocr.verified,
            },
            image_path=image_path,
        )
        return PendingTransaction(
            ledger_id=entry.id,
            quote=quote,
            ocr=ocr,
            receiver_history=history,
            slip_hash=slip_hash,
            image_path=image_path,
            status=status,
        )

    def create_from_thb(self, thb: float) -> PendingTransaction:
        quote = self.rates.from_thb(thb)
        entry = self.store.create_entry(
            slip_hash=None,
            receiver=None,
            bank=None,
            last4=None,
            thb=quote.thb,
            usdt=quote.usdt,
            buy_rate=quote.buy_rate,
            sell_rate=quote.sell_rate,
            profit_pct=quote.profit_pct,
            staff=self.staff_name,
            status="WAITING_USDT",
        )
        return PendingTransaction(
            ledger_id=entry.id,
            quote=quote,
            ocr=None,
            receiver_history=None,
            slip_hash=None,
            image_path=None,
            status="WAITING_USDT",
        )

    def create_from_usdt(self, usdt: float) -> PendingTransaction:
        quote = self.rates.from_usdt(usdt)
        entry = self.store.create_entry(
            slip_hash=None,
            receiver=None,
            bank=None,
            last4=None,
            thb=quote.thb,
            usdt=quote.usdt,
            buy_rate=quote.buy_rate,
            sell_rate=quote.sell_rate,
            profit_pct=quote.profit_pct,
            staff=self.staff_name,
            status="WAITING_USDT",
        )
        return PendingTransaction(
            ledger_id=entry.id,
            quote=quote,
            ocr=None,
            receiver_history=None,
            slip_hash=None,
            image_path=None,
            status="WAITING_USDT",
        )

    def attach_slip_to_pending(
        self,
        ledger_id: str,
        ocr: OCRResult,
        *,
        slip_hash: str | None = None,
        image_path: str | None = None,
    ) -> PendingTransaction:
        entry = self.store.get_entry(ledger_id)
        quote = self.rates.from_thb(ocr.amount_thb or entry.thb)
        history = None
        if ocr.bank and ocr.last4:
            history = self.store.get_receiver(ocr.bank, ocr.last4)
        self.store.update_entry(
            ledger_id,
            thb=quote.thb,
            usdt=quote.usdt,
            buy_rate=quote.buy_rate,
            sell_rate=quote.sell_rate,
            profit_pct=quote.profit_pct,
            receiver=ocr.receiver_name,
            bank=ocr.bank,
            last4=ocr.last4,
            status="OCR_VERIFIED",
        )
        return PendingTransaction(
            ledger_id=ledger_id,
            quote=quote,
            ocr=ocr,
            receiver_history=history,
            slip_hash=slip_hash,
            image_path=image_path,
            status="OCR_VERIFIED",
        )

    def update_amount(
        self,
        ledger_id: str,
        *,
        thb: float | None = None,
        usdt: float | None = None,
    ) -> PendingTransaction:
        quote = self.rates.recalculate(thb, usdt)
        self.store.update_entry(
            ledger_id,
            thb=quote.thb,
            usdt=quote.usdt,
            buy_rate=quote.buy_rate,
            sell_rate=quote.sell_rate,
            profit_pct=quote.profit_pct,
        )
        entry = self.store.get_entry(ledger_id)
        history = None
        if entry.bank and entry.last4:
            history = self.store.get_receiver(entry.bank, entry.last4)
        return PendingTransaction(
            ledger_id=ledger_id,
            quote=quote,
            ocr=None,
            receiver_history=history,
            slip_hash=entry.slip_hash,
            image_path=entry.image_path,
            status=entry.status,
        )

    def confirm(self, ledger_id: str) -> LedgerEntry:
        entry = self.store.get_entry(ledger_id)
        if entry.status == "SETTLED":
            return entry
        self.store.update_entry(ledger_id, status="WAITING_USDT")
        return self.store.settle_entry(ledger_id)

    def cancel(self, ledger_id: str) -> None:
        self.store.delete_entry(ledger_id)

    def get_pending(self, ledger_id: str) -> PendingTransaction:
        entry = self.store.get_entry(ledger_id)
        quote = RateQuote(
            buy_rate=entry.buy_rate,
            sell_rate=entry.sell_rate,
            profit_pct=entry.profit_pct,
            thb=entry.thb,
            usdt=entry.usdt,
        )
        history = None
        if entry.bank and entry.last4:
            history = self.store.get_receiver(entry.bank, entry.last4)
        ocr = None
        if entry.ocr_payload:
            ocr = OCRResult(
                receiver_name=entry.ocr_payload.get("receiver_name"),
                bank=entry.bank,
                last4=entry.last4,
                amount_thb=entry.thb,
                confidence=entry.ocr_confidence or 0.0,
                raw_text=entry.ocr_payload.get("raw_text", ""),
                verified=entry.ocr_payload.get("verified", False),
            )
        return PendingTransaction(
            ledger_id=entry.id,
            quote=quote,
            ocr=ocr,
            receiver_history=history,
            slip_hash=entry.slip_hash,
            image_path=entry.image_path,
            status=entry.status,
        )

    def check_duplicate(self, slip_hash: str) -> str | None:
        return self.store.slip_exists(slip_hash)

    def balance(self) -> dict[str, float]:
        return self.store.totals()
