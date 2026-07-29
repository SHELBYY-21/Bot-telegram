"""Transaction assembly helpers — single place for quote + OCR wiring."""

from __future__ import annotations

from ce_vault.ledger import Ledger, new_ledger_id
from ce_vault.models import OCRResult, Transaction
from ce_vault.rates import quote_from_thb, quote_from_usdt
from ce_vault.theme import TxStatus


def build_from_ocr(
    ledger: Ledger,
    ocr: OCRResult,
    *,
    slip_hash: str,
    staff_id: int | None,
    staff_name: str,
    chat_id: int,
    image_file_id: str = "",
) -> Transaction:
    quote = quote_from_thb(ocr.amount_thb)
    status = TxStatus.OCR_VERIFIED.value if ocr.verified else TxStatus.RECEIVED.value
    tx = Transaction(
        ledger_id=new_ledger_id(),
        status=status,
        thb=quote.thb,
        usdt=quote.usdt,
        buy_rate=quote.buy_rate,
        sell_rate=quote.sell_rate,
        profit_pct=quote.profit_pct,
        receiver_name=ocr.receiver_name,
        bank=ocr.bank,
        last4=ocr.last4,
        confidence=ocr.confidence,
        slip_hash=slip_hash,
        ocr=ocr.to_dict(),
        staff_id=staff_id,
        staff_name=staff_name,
        chat_id=chat_id,
        image_file_id=image_file_id,
    )
    return ledger.create(tx)


def build_from_usdt(
    ledger: Ledger,
    usdt_amount: float,
    *,
    staff_id: int | None,
    staff_name: str,
    chat_id: int,
) -> Transaction:
    quote = quote_from_usdt(usdt_amount)
    tx = Transaction(
        ledger_id=new_ledger_id(),
        status=TxStatus.WAITING_USDT.value,
        thb=quote.thb,
        usdt=quote.usdt,
        buy_rate=quote.buy_rate,
        sell_rate=quote.sell_rate,
        profit_pct=quote.profit_pct,
        staff_id=staff_id,
        staff_name=staff_name,
        chat_id=chat_id,
        confidence=100.0,
    )
    return ledger.create(tx)


def apply_thb_edit(tx: Transaction, thb: float) -> Transaction:
    # Always refresh from live rates on edit so Buy Rate stays automatic
    quote = quote_from_thb(thb)
    tx.thb = quote.thb
    tx.usdt = quote.usdt
    tx.buy_rate = quote.buy_rate
    tx.sell_rate = quote.sell_rate
    tx.profit_pct = quote.profit_pct
    tx.status = TxStatus.OCR_VERIFIED.value if tx.confidence >= 90 else TxStatus.RECEIVED.value
    return tx
