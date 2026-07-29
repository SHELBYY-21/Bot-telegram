"""One-card responses for the CE Vault operations console.

Every render returns a single card. Never mix operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from ce_vault import theme as T
from ce_vault.status import PipelineStatus, render_pipeline


@dataclass
class TxnView:
    ledger_id: str
    thb: Decimal | float | str
    usdt: Decimal | float | str
    buy_rate: Decimal | float | str
    sell_rate: Decimal | float | str
    profit_pct: Decimal | float | str
    receiver: str
    bank: str | None = None
    last4: str | None = None
    confidence: Decimal | float | str | None = None
    status: PipelineStatus | str = PipelineStatus.OCR_VERIFIED
    staff: str | None = None


@dataclass
class OcrView:
    ledger_id: str
    vision: Decimal | float | str
    receiver: str
    bank: str
    last4: str
    amount: Decimal | float | str
    verified: bool = True
    warn: bool = False
    duplicate: bool = False
    repeated_receiver: bool = False
    status: PipelineStatus | str = PipelineStatus.OCR_VERIFIED


@dataclass
class HistoryView:
    receiver: str
    bank: str | None
    last4: str | None
    txn_count: int
    total_thb: Decimal | float | str
    total_usdt: Decimal | float | str
    first_seen: date | datetime | str
    last_seen: date | datetime | str
    risk: str = "LOW"


@dataclass
class SuccessView:
    ledger_id: str
    profit_pct: Decimal | float | str
    balance_usdt: Decimal | float | str | None = None
    balance_thb: Decimal | float | str | None = None


@dataclass
class ErrorView:
    problem: str
    cause: str
    action: str


@dataclass
class EditView:
    ledger_id: str
    fields: dict[str, Any]


@dataclass
class DeleteView:
    ledger_id: str
    thb: Decimal | float | str
    usdt: Decimal | float | str
    receiver: str


@dataclass
class ProgressView:
    ledger_id: str | None
    status: PipelineStatus | str
    detail: str | None = None


def receive_card(
    *,
    ledger_id: str | None = None,
    detail: str = "Slip captured",
    brand: str = "CE VAULT",
    subtitle: str = "Secure Ledger",
) -> str:
    body = [
        T.header(brand, subtitle, ledger_id),
        render_pipeline(PipelineStatus.RECEIVED),
        T.RULE,
        T.field("Intake", detail),
    ]
    return "\n".join(body)


def progress_card(view: ProgressView, *, brand: str = "CE VAULT", subtitle: str = "Secure Ledger") -> str:
    lines = [
        T.header(brand, subtitle, view.ledger_id),
        render_pipeline(view.status),
    ]
    if view.detail:
        lines.extend([T.RULE, T.field("Progress", view.detail)])
    return "\n".join(lines)


def ocr_card(view: OcrView, *, brand: str = "CE VAULT", subtitle: str = "Secure Ledger") -> str:
    vision_s = f"{float(view.vision):.1f}%"
    status_label = "Verified" if view.verified else "Review"
    lines = [
        T.header(brand, subtitle, view.ledger_id),
        render_pipeline(view.status),
        T.RULE,
        T.field("Vision", vision_s, code=True),
        "",
        T.field("Receiver", view.receiver),
        "",
        T.field("Bank", view.bank),
        "",
        T.field("Last4", view.last4, code=True),
        "",
        T.field("Detected Amount", T.money(view.amount), code=True),
        "",
        T.field("Status", status_label),
    ]
    if view.warn:
        lines.extend(["", T.title("Confidence below threshold")])
    if view.duplicate:
        lines.extend(["", T.title("Duplicate slip detected")])
    if view.repeated_receiver:
        lines.extend(["", T.title("Receiver on file")])
    return "\n".join(lines)


def transaction_card(view: TxnView, *, brand: str = "CE VAULT", subtitle: str = "Secure Ledger") -> str:
    receiver = view.receiver
    if view.bank or view.last4:
        receiver = T.mask_account(view.last4 or "", view.bank) if view.last4 else view.receiver

    lines = [
        T.header(brand, subtitle, view.ledger_id),
        render_pipeline(view.status),
        T.RULE,
        T.field("THB", T.money(view.thb), code=True),
        "",
        T.field("USDT", T.crypto(view.usdt), code=True),
        "",
        T.field("Buy Rate", T.money(view.buy_rate), code=True),
        "",
        T.field("Sell Rate", T.money(view.sell_rate), code=True),
        "",
        T.field("Profit", T.pct(view.profit_pct), code=True),
        "",
        T.field("Receiver", receiver),
    ]
    if view.confidence is not None:
        lines.extend(["", T.field("Confidence", f"{float(view.confidence):.1f}%", code=True)])
    return "\n".join(lines)


def confirmation_card(view: TxnView, *, brand: str = "CE VAULT", subtitle: str = "Secure Ledger") -> str:
    """Confirmation layout — same transaction metrics, decision-ready."""
    return transaction_card(view, brand=brand, subtitle=subtitle)


def success_card(view: SuccessView, *, brand: str = "CE VAULT", subtitle: str = "Secure Ledger") -> str:
    lines = [
        T.header(brand, subtitle, view.ledger_id),
        "",
        "● " + T.title("SETTLED"),
        "",
        T.RULE,
        T.field("Ledger ID", view.ledger_id, code=True),
        "",
        T.field("Profit", T.pct(view.profit_pct), code=True),
    ]
    if view.balance_usdt is not None:
        lines.extend(["", T.field("Updated Balance", f"{T.crypto(view.balance_usdt)} USDT", code=True)])
    elif view.balance_thb is not None:
        lines.extend(["", T.field("Updated Balance", f"{T.money(view.balance_thb)} THB", code=True)])
    lines.extend(["", T.title("Done.")])
    return "\n".join(lines)


def history_card(view: HistoryView, *, brand: str = "CE VAULT", subtitle: str = "Secure Ledger") -> str:
    receiver = (
        T.mask_account(view.last4, view.bank)
        if view.last4
        else view.receiver
    )
    first = _fmt_day(view.first_seen)
    last = _fmt_day(view.last_seen, relative_today=True)
    lines = [
        T.header(brand, subtitle),
        T.field("Receiver", receiver),
        "",
        T.field("Activity", f"{view.txn_count} Transactions"),
        "",
        T.field("Volume THB", T.money(view.total_thb), code=True),
        "",
        T.field("Volume USDT", T.crypto(view.total_usdt), code=True),
        "",
        T.field("First Seen", first),
        "",
        T.field("Last Seen", last),
        "",
        T.field("Risk", view.risk.upper()),
    ]
    return "\n".join(lines)


def error_card(view: ErrorView, *, brand: str = "CE VAULT", subtitle: str = "Secure Ledger") -> str:
    lines = [
        T.header(brand, subtitle),
        "● " + T.title("ERROR"),
        T.RULE,
        T.field("Problem", view.problem),
        "",
        T.field("Cause", view.cause),
        "",
        T.field("Action", view.action),
    ]
    return "\n".join(lines)


def edit_card(view: EditView, *, brand: str = "CE VAULT", subtitle: str = "Secure Ledger") -> str:
    lines = [
        T.header(brand, subtitle, view.ledger_id),
        T.title("EDIT"),
        T.RULE,
    ]
    for key, value in view.fields.items():
        code = key.lower() in {"thb", "usdt", "buy_rate", "sell_rate", "profit", "last4", "confidence"}
        display = value
        if key.lower() in {"thb", "buy_rate", "sell_rate"}:
            display = T.money(value)
        elif key.lower() == "usdt":
            display = T.crypto(value)
        lines.extend(["", T.field(key.replace("_", " ").title(), display, code=code)])
    lines.extend(["", T.label("Reply with field=value to update")])
    return "\n".join(lines)


def delete_card(view: DeleteView, *, brand: str = "CE VAULT", subtitle: str = "Secure Ledger") -> str:
    lines = [
        T.header(brand, subtitle, view.ledger_id),
        T.title("DELETE"),
        T.RULE,
        T.field("Ledger ID", view.ledger_id, code=True),
        "",
        T.field("THB", T.money(view.thb), code=True),
        "",
        T.field("USDT", T.crypto(view.usdt), code=True),
        "",
        T.field("Receiver", view.receiver),
        "",
        T.label("This action removes the ledger entry."),
    ]
    return "\n".join(lines)


def console_home(*, buy_rate: Decimal | float, sell_rate: Decimal | float, open_count: int = 0) -> str:
    lines = [
        T.header(),
        T.field("Desk", "Operations Console"),
        T.RULE,
        T.field("Buy Rate", T.money(buy_rate), code=True),
        "",
        T.field("Sell Rate", T.money(sell_rate), code=True),
        "",
        T.field("Open Ledgers", str(open_count), code=True),
        T.RULE,
        T.label("Send a slip photo — or USDT amount"),
    ]
    return "\n".join(lines)


def _fmt_day(value: date | datetime | str, *, relative_today: bool = False) -> str:
    if isinstance(value, datetime):
        d = value.date()
    elif isinstance(value, date):
        d = value
    else:
        text = str(value)
        if relative_today and text.lower() in {"today", "วันนี้"}:
            return "Today"
        return text
    if relative_today and d == date.today():
        return "Today"
    return d.isoformat()
