"""CE VAULT card layouts — one card per message, one decision per screen."""

from __future__ import annotations

from ce_vault.config import CONFIDENCE_WARN_THRESHOLD
from ce_vault.models import OCRResult, ReceiverHistory, Transaction
from ce_vault.ui.status import status_rail
from ce_vault.ui.theme import (
    RULE,
    THIN,
    esc,
    fmt_confidence,
    fmt_day,
    fmt_pct,
    fmt_rate,
    fmt_thb,
    fmt_usdt,
    header,
    label,
    mono,
    progress_bar,
    value_block,
)


def receive_card(tx: Transaction, *, progress: float | None = None) -> str:
    """Inbound slip — awaiting OCR."""
    parts = [
        header(tx.ledger_id),
        status_rail(tx.status),
        RULE,
        value_block("Channel", "Slip Intake"),
        "",
        value_block("Staff", tx.staff or "—"),
    ]
    if progress is not None:
        parts.extend(
            [
                "",
                label("Progress"),
                f"{progress_bar(progress)} {mono(f'{int(progress * 100)}%')}",
            ]
        )
    else:
        parts.extend(["", label("State"), mono("INGESTING")])
    return "\n".join(parts)


def ocr_card(tx: Transaction, ocr: OCRResult) -> str:
    """Vision result — numbers only, no paragraphs."""
    warn = ""
    if ocr.confidence and ocr.confidence < CONFIDENCE_WARN_THRESHOLD:
        warn = f"\n\n{label('Alert')}\n{mono('CONFIDENCE BELOW 90%')}"

    status_line = "Verified" if ocr.verified else "Review"
    parts = [
        header(tx.ledger_id, subtitle="Vision Desk"),
        status_rail(tx.status),
        RULE,
        value_block("Vision", fmt_confidence(ocr.confidence), large=True),
        "",
        value_block("Receiver", ocr.receiver_name or "—"),
        "",
        value_block("Bank", ocr.bank or "—"),
        "",
        value_block("Last4", ocr.last4 or "—"),
        "",
        value_block("Detected Amount", fmt_thb(ocr.amount_thb), large=True),
        "",
        value_block("Status", status_line),
        warn,
    ]
    return "\n".join(p for p in parts if p is not None)


def confirmation_card(tx: Transaction) -> str:
    """Transaction desk — confirm / edit / cancel."""
    parts = [
        header(tx.ledger_id),
        status_rail(tx.status),
        RULE,
        value_block("THB", fmt_thb(tx.thb), large=True),
        "",
        value_block("USDT", fmt_usdt(tx.usdt), large=True),
        "",
        value_block("Buy Rate", fmt_rate(tx.buy_rate)),
        "",
        value_block("Sell Rate", fmt_rate(tx.sell_rate)),
        "",
        value_block("Profit", fmt_pct(tx.profit_pct)),
        "",
        value_block("Receiver", tx.receiver_mask()),
        "",
        value_block("Confidence", fmt_confidence(tx.confidence)),
    ]
    if tx.confidence is not None and tx.confidence < CONFIDENCE_WARN_THRESHOLD:
        parts.extend(["", label("Alert"), mono("REVIEW REQUIRED")])
    return "\n".join(parts)


def success_card(
    tx: Transaction,
    *,
    updated_balance_usdt: float | None = None,
) -> str:
    """Minimal settlement receipt."""
    parts = [
        header(tx.ledger_id),
        status_rail(tx.status),
        RULE,
        "<b>● SETTLED</b>",
        "",
        value_block("Ledger ID", tx.ledger_id),
        "",
        value_block("Profit", fmt_pct(tx.profit_pct)),
        "",
        value_block(
            "Updated Balance",
            fmt_usdt(updated_balance_usdt)
            if updated_balance_usdt is not None
            else fmt_usdt(tx.usdt),
        ),
        "",
        THIN,
        "<b>Done.</b>",
    ]
    return "\n".join(parts)


def history_card(hist: ReceiverHistory) -> str:
    """Counterparty dossier — one receiver, one card."""
    parts = [
        header(subtitle="Counterparty"),
        value_block("Receiver", f"{hist.bank} ••••{hist.last4}", large=True),
        "",
        value_block("Identity", hist.receiver_name or "—"),
        RULE,
        value_block("Volume", f"{hist.tx_count} Transactions"),
        "",
        value_block("THB", fmt_thb(hist.total_thb), large=True),
        "",
        value_block("USDT", fmt_usdt(hist.total_usdt), large=True),
        RULE,
        value_block("First Seen", fmt_day(hist.first_seen)),
        "",
        value_block("Last Seen", fmt_day(hist.last_seen)),
        "",
        value_block("Risk", hist.risk),
    ]
    return "\n".join(parts)


def error_card(*, problem: str, cause: str, action: str, ledger_id: str | None = None) -> str:
    """Only Problem / Cause / Action."""
    parts = [
        header(ledger_id, subtitle="Exception"),
        value_block("Problem", problem),
        "",
        value_block("Cause", cause),
        "",
        value_block("Action", action),
    ]
    return "\n".join(parts)


def edit_card(tx: Transaction, field: str = "amount") -> str:
    """Single-field edit prompt."""
    field_label = {
        "amount": "THB Amount",
        "usdt": "USDT Amount",
        "receiver": "Receiver Name",
        "bank": "Bank",
        "last4": "Last4",
    }.get(field, field)
    parts = [
        header(tx.ledger_id, subtitle="Amend"),
        status_rail(tx.status),
        RULE,
        value_block("Editing", field_label),
        "",
        value_block("Current THB", fmt_thb(tx.thb)),
        "",
        value_block("Current USDT", fmt_usdt(tx.usdt)),
        "",
        label("Input"),
        mono("awaiting value…"),
    ]
    return "\n".join(parts)


def delete_card(tx: Transaction) -> str:
    """Destructive confirm — one decision."""
    parts = [
        header(tx.ledger_id, subtitle="Void"),
        status_rail(tx.status),
        RULE,
        value_block("THB", fmt_thb(tx.thb)),
        "",
        value_block("USDT", fmt_usdt(tx.usdt)),
        "",
        value_block("Receiver", tx.receiver_mask()),
        RULE,
        label("Decision"),
        mono("VOID THIS LEDGER ENTRY?"),
    ]
    return "\n".join(parts)


def loading_card(title: str = "Processing", ratio: float = 0.35, ledger_id: str | None = None) -> str:
    parts = [
        header(ledger_id, subtitle="Console"),
        label(title),
        f"{progress_bar(ratio)} {mono(f'{int(ratio * 100)}%')}",
    ]
    return "\n".join(parts)


def rates_card(buy: float, sell: float, profit_pct: float) -> str:
    parts = [
        header(subtitle="Market Desk"),
        value_block("Buy Rate", fmt_rate(buy), large=True),
        "",
        value_block("Sell Rate", fmt_rate(sell), large=True),
        "",
        value_block("Spread", fmt_pct(profit_pct)),
        RULE,
        label("Policy"),
        mono("Buy rate is never requested from operators."),
    ]
    return "\n".join(parts)


def console_home(buy: float, sell: float, open_count: int, settled_today: int) -> str:
    """Start screen — one composition, not a chatbot greeting."""
    parts = [
        header(subtitle="Secure Ledger"),
        label("Operations Console"),
        RULE,
        value_block("Buy", fmt_rate(buy)),
        "",
        value_block("Sell", fmt_rate(sell)),
        RULE,
        value_block("Open", str(open_count)),
        "",
        value_block("Settled Today", str(settled_today)),
        RULE,
        label("Intake"),
        mono("Slip photo  ·  USDT amount"),
    ]
    return "\n".join(parts)


def typing_indicator() -> str:
    return f"{header(subtitle='Console')}\n{label('Working')}\n{mono('···')}"
