"""Premium card renderers for CE VAULT."""

from __future__ import annotations

from db.ledger import LedgerEntry, ReceiverHistory
from services.ocr import OCRResult
from services.rates import RateQuote
from services.transaction import PendingTransaction
from ui import theme


def receive_card(ledger_id: str) -> str:
    return "\n".join(
        [
            theme.header(ledger_id),
            theme.status_pipeline("RECEIVED"),
            "",
            "Slip received",
            "Processing…",
        ]
    )


def loading_card(ledger_id: str, stage: str) -> str:
    return "\n".join(
        [
            theme.header(ledger_id),
            theme.status_pipeline("RECEIVED"),
            "",
            stage,
            "▌",
        ]
    )


def ocr_card(ledger_id: str, ocr: OCRResult, *, warn: bool = False) -> str:
    status = "Verified" if ocr.verified else "Review"
    lines = [
        theme.header(ledger_id),
        theme.status_pipeline("OCR_VERIFIED"),
        "",
        f"Vision        {theme.mono(f'{ocr.confidence:.1f}%')}",
        f"Receiver      {theme.esc(ocr.receiver_name or '—')}",
        f"Bank          {theme.esc(ocr.bank or '—')}",
        f"Last4         {theme.mono(ocr.last4 or '—')}",
        f"Detected Amt  {theme.mono(theme.format_thb(ocr.amount_thb or 0))}",
        f"Status        {theme.esc(status)}",
    ]
    if warn or ocr.confidence < 90:
        lines.append("")
        lines.append("<b>Low confidence — verify before confirming</b>")
    return "\n".join(lines)


def transaction_card(
    pending: PendingTransaction,
    *,
    active_status: str = "WAITING_USDT",
    confidence: float | None = None,
) -> str:
    q = pending.quote
    receiver = "—"
    if pending.ocr and pending.ocr.masked_receiver:
        receiver = pending.ocr.masked_receiver
    elif pending.receiver_history:
        receiver = pending.receiver_history.masked
    conf = confidence if confidence is not None else (pending.ocr.confidence if pending.ocr else None)

    lines = [
        theme.header(pending.ledger_id),
        theme.status_pipeline(active_status),
        "",
        f"THB           {theme.mono(theme.format_thb(q.thb))}",
        f"USDT          {theme.mono(theme.format_usdt(q.usdt))}",
        "",
        f"Buy Rate      {theme.mono(f'{q.buy_rate:.2f}')}",
        f"Sell Rate     {theme.mono(f'{q.sell_rate:.2f}')}",
        f"Profit        {theme.mono(theme.format_pct(q.profit_pct))}",
        "",
        f"Receiver      {theme.esc(receiver)}",
    ]
    if conf is not None:
        lines.append(f"Confidence    {theme.mono(f'{conf:.1f}%')}")
    if pending.receiver_history:
        h = pending.receiver_history
        lines.append("")
        lines.append(f"History       {theme.mono(h.tx_count)} tx · {theme.esc(h.risk_level)} risk")
    lines.append(theme.divider())
    return "\n".join(lines)


def history_card(history: ReceiverHistory) -> str:
    return "\n".join(
        [
            theme.header(),
            "History",
            theme.divider(),
            f"Receiver      {theme.esc(history.masked)}",
            f"Transactions  {theme.mono(history.tx_count)}",
            f"Volume THB    {theme.mono(theme.format_thb(history.total_thb))}",
            f"Volume USDT   {theme.mono(theme.format_usdt(history.total_usdt))}",
            "",
            f"First Seen    {theme.esc(theme.format_date(history.first_seen))}",
            f"Last Seen     {theme.esc(theme.format_date(history.last_seen))}",
            f"Risk          {theme.esc(history.risk_level)}",
        ]
    )


def success_card(entry: LedgerEntry, balance: dict[str, float]) -> str:
    return "\n".join(
        [
            theme.header(entry.id),
            theme.status_pipeline("SETTLED"),
            "",
            "<b>SETTLED</b>",
            "",
            f"Ledger ID     {theme.mono(entry.id)}",
            f"Profit        {theme.mono(theme.format_pct(entry.profit_pct))}",
            f"Balance THB   {theme.mono(theme.format_thb(balance['total_thb']))}",
            f"Balance USDT  {theme.mono(theme.format_usdt(balance['total_usdt']))}",
            "",
            "Done.",
        ]
    )


def error_card(
    *,
    problem: str,
    cause: str,
    action: str,
    ledger_id: str | None = None,
) -> str:
    return "\n".join(
        [
            theme.header(ledger_id),
            "<b>Error</b>",
            theme.divider(),
            f"Problem       {theme.esc(problem)}",
            f"Cause         {theme.esc(cause)}",
            f"Action        {theme.esc(action)}",
        ]
    )


def edit_card(pending: PendingTransaction) -> str:
    q = pending.quote
    return "\n".join(
        [
            theme.header(pending.ledger_id),
            "Edit",
            theme.divider(),
            f"THB           {theme.mono(theme.format_thb(q.thb))}",
            f"USDT          {theme.mono(theme.format_usdt(q.usdt))}",
            "",
            "Send new THB or USDT amount to update.",
            "Example: 500 or 12.5342",
        ]
    )


def delete_card(ledger_id: str) -> str:
    return "\n".join(
        [
            theme.header(ledger_id),
            "Delete",
            theme.divider(),
            "Cancel this ledger entry?",
        ]
    )


def console_home() -> str:
    return "\n".join(
        [
            theme.header(),
            "Operations Console",
            theme.divider(),
            "",
            "Send a payment slip image",
            "or enter a USDT amount.",
            "",
            "Everything else is automatic.",
        ]
    )
