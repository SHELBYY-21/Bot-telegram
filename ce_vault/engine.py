"""Domain orchestration — slip intake, USDT intake, settle, edit."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from ce_vault.cards import (
    DeleteView,
    ErrorView,
    HistoryView,
    OcrView,
    ProgressView,
    SuccessView,
    TxnView,
    confirmation_card,
    delete_card,
    error_card,
    history_card,
    ocr_card,
    progress_card,
    receive_card,
    success_card,
)
from ce_vault.ledger import LedgerRecord, LedgerStore
from ce_vault.ocr import OcrResult, run_ocr, slip_hash
from ce_vault.rates import RateBook
from ce_vault.status import PipelineStatus


@dataclass
class DeskState:
    store: LedgerStore
    rates: RateBook
    ocr_api_key: str | None = None
    ocr_model: str = "gpt-4o-mini"
    ocr_warn_below: float = 90.0


def txn_view(record: LedgerRecord) -> TxnView:
    return TxnView(
        ledger_id=record.id,
        thb=record.thb or Decimal("0"),
        usdt=record.usdt or Decimal("0"),
        buy_rate=record.buy_rate or Decimal("0"),
        sell_rate=record.sell_rate or Decimal("0"),
        profit_pct=record.profit_pct or Decimal("0"),
        receiver=record.receiver_name or "—",
        bank=record.bank,
        last4=record.last4,
        confidence=record.confidence,
        status=record.status,
        staff=record.staff_name,
    )


def apply_rates(desk: DeskState, thb: Decimal) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    usdt = desk.rates.thb_to_usdt(thb)
    return thb, usdt, desk.rates.buy_rate, desk.rates.sell_rate


def enrich_from_ocr(desk: DeskState, record: LedgerRecord, ocr: OcrResult) -> LedgerRecord:
    thb = ocr.amount_thb
    fields: dict[str, Any] = {
        "ocr_json": ocr.to_dict(),
        "receiver_name": ocr.receiver_name,
        "bank": ocr.bank,
        "last4": ocr.last4,
        "confidence": ocr.confidence,
        "status": PipelineStatus.OCR_VERIFIED.value
        if ocr.amount_thb and ocr.confidence >= desk.ocr_warn_below
        else PipelineStatus.OCR_VERIFIED.value,
        "buy_rate": desk.rates.buy_rate,
        "sell_rate": desk.rates.sell_rate,
        "profit_pct": desk.rates.profit_pct(),
    }
    if thb is not None:
        _, usdt, buy, sell = apply_rates(desk, thb)
        fields.update({"thb": thb, "usdt": usdt, "buy_rate": buy, "sell_rate": sell})
    return desk.store.update(record.id, **fields)


async def intake_slip(
    desk: DeskState,
    *,
    image_bytes: bytes | None,
    caption: str | None,
    staff_id: int | None,
    staff_name: str | None,
    chat_id: int | None,
    mime: str = "image/jpeg",
) -> tuple[LedgerRecord, str, bool]:
    """Create ledger from slip. Returns (record, card_html, is_duplicate)."""
    digest = slip_hash(image_bytes or (caption or "").encode())
    dup = desk.store.find_by_slip_hash(digest)

    record = desk.store.create(
        status=PipelineStatus.RECEIVED.value,
        staff_id=staff_id,
        staff_name=staff_name,
        chat_id=chat_id,
        slip_hash=digest,
    )

    ocr = await run_ocr(
        image_bytes=image_bytes,
        caption=caption,
        api_key=desk.ocr_api_key,
        model=desk.ocr_model,
        mime=mime,
    )
    record = enrich_from_ocr(desk, record, ocr)

    warn = (ocr.confidence or 0) < desk.ocr_warn_below
    prior = desk.store.get_receiver(ocr.bank, ocr.last4, ocr.receiver_name)
    view = OcrView(
        ledger_id=record.id,
        vision=ocr.confidence,
        receiver=ocr.receiver_name or "—",
        bank=ocr.bank or "—",
        last4=ocr.last4 or "————",
        amount=ocr.amount_thb or Decimal("0"),
        verified=not warn and ocr.amount_thb is not None,
        warn=warn,
        duplicate=dup is not None,
        repeated_receiver=prior is not None and prior.txn_count > 0,
        status=PipelineStatus.OCR_VERIFIED,
    )
    # After OCR card, next decision screen is confirmation when amount present
    return record, ocr_card(view), dup is not None


def confirmation_from_record(record: LedgerRecord) -> str:
    return confirmation_card(txn_view(record))


def intake_usdt(desk: DeskState, usdt_amount: Decimal, *, staff_id: int | None, staff_name: str | None, chat_id: int | None) -> tuple[LedgerRecord, str]:
    thb = desk.rates.usdt_to_thb(usdt_amount)
    usdt = usdt_amount
    record = desk.store.create(
        status=PipelineStatus.WAITING_USDT.value,
        staff_id=staff_id,
        staff_name=staff_name,
        chat_id=chat_id,
    )
    record = desk.store.update(
        record.id,
        thb=thb,
        usdt=usdt,
        buy_rate=desk.rates.buy_rate,
        sell_rate=desk.rates.sell_rate,
        profit_pct=desk.rates.profit_pct(),
        receiver_name="USDT desk",
        status=PipelineStatus.WAITING_USDT.value,
    )
    return record, confirmation_card(txn_view(record))


def parse_usdt_message(text: str) -> Decimal | None:
    raw = text.strip().replace(",", "")
    raw = raw.upper().replace("USDT", "").strip()
    if not raw:
        return None
    # Require a clear numeric intent — avoid swallowing random chat
    if not any(ch.isdigit() for ch in raw):
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    if value <= 0:
        return None
    return value


def settle(desk: DeskState, ledger_id: str) -> tuple[LedgerRecord, str]:
    record = desk.store.settle(ledger_id)
    _, usdt_bal = desk.store.balance_totals()
    card = success_card(
        SuccessView(
            ledger_id=record.id,
            profit_pct=record.profit_pct or Decimal("0"),
            balance_usdt=usdt_bal,
        )
    )
    return record, card


def cancel(desk: DeskState, ledger_id: str) -> tuple[LedgerRecord, str]:
    record = desk.store.cancel(ledger_id)
    card = error_card(
        ErrorView(
            problem="Ledger cancelled",
            cause=f"{ledger_id} was voided by operator",
            action="No funds moved. Send a new slip to reopen.",
        )
    )
    return record, card


def prepare_delete(desk: DeskState, ledger_id: str) -> str | None:
    record = desk.store.get(ledger_id)
    if not record:
        return None
    return delete_card(
        DeleteView(
            ledger_id=record.id,
            thb=record.thb or Decimal("0"),
            usdt=record.usdt or Decimal("0"),
            receiver=record.receiver_name or T_mask(record),
        )
    )


def T_mask(record: LedgerRecord) -> str:
    from ce_vault.theme import mask_account

    if record.last4:
        return mask_account(record.last4, record.bank)
    return record.receiver_name or "—"


def apply_edit(desk: DeskState, ledger_id: str, patch: dict[str, str]) -> tuple[LedgerRecord | None, str]:
    record = desk.store.get(ledger_id)
    if not record:
        return None, error_card(ErrorView("Ledger missing", f"{ledger_id} not found", "Check ID and retry"))

    fields: dict[str, Any] = {}
    for key, value in patch.items():
        k = key.lower().strip()
        if k in {"thb", "amount"}:
            fields["thb"] = Decimal(value.replace(",", ""))
        elif k == "usdt":
            fields["usdt"] = Decimal(value.replace(",", ""))
        elif k in {"receiver", "receiver_name", "name"}:
            fields["receiver_name"] = value
        elif k == "bank":
            fields["bank"] = value.upper()
        elif k == "last4":
            fields["last4"] = "".join(c for c in value if c.isdigit())[-4:]
        elif k == "buy_rate":
            # Allowed for admin override only via explicit edit — not asked in normal flow
            fields["buy_rate"] = Decimal(value)
        elif k == "sell_rate":
            fields["sell_rate"] = Decimal(value)

    if "thb" in fields and "usdt" not in fields:
        fields["usdt"] = desk.rates.thb_to_usdt(fields["thb"])
        fields.setdefault("buy_rate", desk.rates.buy_rate)
        fields.setdefault("sell_rate", desk.rates.sell_rate)
        fields["profit_pct"] = desk.rates.profit_pct()
    elif "usdt" in fields and "thb" not in fields:
        buy = Decimal(str(fields.get("buy_rate", record.buy_rate or desk.rates.buy_rate)))
        fields["thb"] = (fields["usdt"] * buy).quantize(Decimal("0.01"))
        fields.setdefault("buy_rate", buy)
        fields.setdefault("sell_rate", desk.rates.sell_rate)
        fields["profit_pct"] = desk.rates.profit_pct()

    record = desk.store.update(ledger_id, **fields)
    return record, confirmation_card(txn_view(record))


def history_for(desk: DeskState, bank: str | None, last4: str | None, name: str | None = None) -> str:
    stats = desk.store.receiver_history(bank, last4, name)
    if not stats:
        return error_card(
            ErrorView(
                problem="No history",
                cause="Receiver has no settled ledgers",
                action="Complete a settlement first",
            )
        )
    from datetime import date, datetime

    def as_day(s: str):
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        except ValueError:
            return s

    return history_card(
        HistoryView(
            receiver=stats.receiver_name or "—",
            bank=stats.bank,
            last4=stats.last4,
            txn_count=stats.txn_count,
            total_thb=stats.total_thb,
            total_usdt=stats.total_usdt,
            first_seen=as_day(stats.first_seen),
            last_seen=as_day(stats.last_seen),
            risk=stats.risk,
        )
    )


def progress(ledger_id: str | None, status: PipelineStatus, detail: str | None = None) -> str:
    return progress_card(ProgressView(ledger_id=ledger_id, status=status, detail=detail))


def receive(ledger_id: str | None = None) -> str:
    return receive_card(ledger_id=ledger_id)
