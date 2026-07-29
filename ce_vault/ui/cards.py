"""Premium card layouts — one card per message, one decision per screen."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ce_vault.theme import (
    CONFIDENCE_WARN_THRESHOLD,
    RULE,
    esc,
    field,
    header,
    mask_account,
    money,
    money_code,
    pct_code,
    to_decimal,
    truncate,
)
from ce_vault.ui.status import PipelineStatus, render_pipeline, render_single


@dataclass
class TxDraft:
    ledger_id: str
    thb: Decimal
    usdt: Decimal
    buy_rate: Decimal
    sell_rate: Decimal
    profit_pct: Decimal
    receiver: str
    bank: str
    last4: str
    confidence: Decimal | None = None
    status: PipelineStatus = PipelineStatus.WAITING_USDT
    staff: str | None = None


@dataclass
class OcrResultView:
    ledger_id: str
    confidence: Decimal
    receiver: str
    bank: str
    last4: str
    amount_thb: Decimal
    verified: bool
    warning: str | None = None
    duplicate: bool = False


@dataclass
class HistoryView:
    receiver_mask: str
    tx_count: int
    total_thb: Decimal
    total_usdt: Decimal
    first_seen: str
    last_seen: str
    risk: str


@dataclass
class SuccessView:
    ledger_id: str
    profit_pct: Decimal
    balance_usdt: Decimal
    thb: Decimal | None = None
    usdt: Decimal | None = None


@dataclass
class ErrorView:
    problem: str
    cause: str
    action: str


def card_receive(ledger_id: str, note: str | None = None) -> str:
    body = [
        header(ledger_id),
        render_pipeline(PipelineStatus.RECEIVED),
        "",
        field("Channel", "<code>SLIP · USDT</code>"),
        field("Mode", "<code>AUTO SETTLE</code>"),
    ]
    if note:
        body.extend(["", field("Note", f"<code>{esc(note)}</code>")])
    return "\n".join(body)


def card_ocr(view: OcrResultView) -> str:
    conf = to_decimal(view.confidence)
    conf_line = f"<code>{esc(money(conf, 1))}%</code>"
    if conf < CONFIDENCE_WARN_THRESHOLD:
        conf_line += "  <b>LOW</b>"

    status_label = "Verified" if view.verified else "Review"
    if view.duplicate:
        status_label = "Duplicate"

    lines = [
        header(view.ledger_id),
        render_pipeline(PipelineStatus.OCR_VERIFIED if view.verified else PipelineStatus.RECEIVED),
        "",
        field("Vision", conf_line),
        field("Receiver", f"<code>{esc(truncate(view.receiver, 32))}</code>"),
        field("Bank", f"<code>{esc(view.bank)}</code>"),
        field("Last4", f"<code>{esc(view.last4)}</code>"),
        field("Detected Amount", money_code(view.amount_thb, 2)),
        field("Status", f"<code>{esc(status_label)}</code>"),
    ]
    if view.warning:
        lines.extend(["", f"<b>{esc(view.warning)}</b>"])
    return "\n".join(lines)


def card_transaction(draft: TxDraft) -> str:
    conf = ""
    if draft.confidence is not None:
        conf = "\n" + field(
            "Confidence",
            f"<code>{esc(money(draft.confidence, 1))}%</code>",
        )

    return "\n".join(
        [
            header(draft.ledger_id),
            render_pipeline(draft.status),
            "",
            field("THB", money_code(draft.thb, 2)),
            field("USDT", money_code(draft.usdt, 4)),
            field("Buy Rate", money_code(draft.buy_rate, 2)),
            field("Sell Rate", money_code(draft.sell_rate, 2)),
            field("Profit", pct_code(draft.profit_pct, 2)),
            field("Receiver", f"<code>{mask_account(draft.last4, draft.bank)}</code>"),
            conf.lstrip("\n") if conf else "",
        ]
    ).rstrip()


def card_confirmation(draft: TxDraft) -> str:
    """Confirmation is a transaction card at WAITING USDT — one decision."""
    draft.status = PipelineStatus.WAITING_USDT
    body = card_transaction(draft)
    return body + f"\n{RULE}\n<i>Confirm · Edit · Cancel</i>"


def card_success(view: SuccessView) -> str:
    lines = [
        header(view.ledger_id),
        render_single(PipelineStatus.SETTLED, glow=True),
        "",
        "<b>✓ SETTLED</b>",
        "",
        field("Ledger ID", f"<code>{esc(view.ledger_id)}</code>"),
        field("Profit", pct_code(view.profit_pct, 2)),
        field("Updated Balance", money_code(view.balance_usdt, 4) + " USDT"),
        "",
        "<i>Done.</i>",
    ]
    return "\n".join(lines)


def card_history(view: HistoryView, ledger_id: str | None = None) -> str:
    risk = view.risk.upper()
    return "\n".join(
        [
            header(ledger_id, subtitle="Receiver History"),
            field("Receiver", f"<code>{esc(view.receiver_mask)}</code>"),
            "",
            field("Volume", f"<code>{view.tx_count}</code> Transactions"),
            field("THB", money_code(view.total_thb, 2)),
            field("USDT", money_code(view.total_usdt, 4)),
            "",
            field("First Seen", f"<code>{esc(view.first_seen)}</code>"),
            field("Last Seen", f"<code>{esc(view.last_seen)}</code>"),
            field("Risk", f"<code>{esc(risk)}</code>"),
        ]
    )


def card_error(view: ErrorView, ledger_id: str | None = None) -> str:
    return "\n".join(
        [
            header(ledger_id, subtitle="Exception"),
            render_single(PipelineStatus.ERROR, glow=True),
            "",
            field("Problem", f"<code>{esc(view.problem)}</code>"),
            field("Cause", f"<code>{esc(view.cause)}</code>"),
            field("Action", f"<code>{esc(view.action)}</code>"),
        ]
    )


def card_edit(draft: TxDraft) -> str:
    draft.status = PipelineStatus.EDITING
    return "\n".join(
        [
            header(draft.ledger_id, subtitle="Edit Entry"),
            render_single(PipelineStatus.EDITING, glow=True),
            "",
            field("THB", money_code(draft.thb, 2)),
            field("USDT", money_code(draft.usdt, 4)),
            field("Sell Rate", money_code(draft.sell_rate, 2)),
            field("Receiver", f"<code>{mask_account(draft.last4, draft.bank)}</code>"),
            "",
            "<i>Send new USDT amount, or Cancel.</i>",
        ]
    )


def card_delete(ledger_id: str, receiver_mask: str) -> str:
    return "\n".join(
        [
            header(ledger_id, subtitle="Delete Entry"),
            render_single(PipelineStatus.DELETED, glow=True),
            "",
            field("Target", f"<code>{esc(ledger_id)}</code>"),
            field("Receiver", f"<code>{esc(receiver_mask)}</code>"),
            "",
            "<i>This action is permanent.</i>",
        ]
    )


def card_loading(ledger_id: str | None, stage: str = "Processing") -> str:
    return "\n".join(
        [
            header(ledger_id),
            f"<b>● {esc(stage.upper())}</b>",
            "",
            "<code>················</code>",
            "<i>Working…</i>",
        ]
    )


def card_console_home(balance_usdt: Decimal, open_count: int, settled_today: int) -> str:
    return "\n".join(
        [
            header(subtitle="Operations Console"),
            field("Balance", money_code(balance_usdt, 4) + " USDT"),
            field("Open", f"<code>{open_count}</code>"),
            field("Settled Today", f"<code>{settled_today}</code>"),
            RULE,
            "<i>Send slip image  ·  or USDT amount</i>",
        ]
    )


def draft_from_record(rec: dict[str, Any]) -> TxDraft:
    return TxDraft(
        ledger_id=str(rec["ledger_id"]),
        thb=to_decimal(rec.get("thb")),
        usdt=to_decimal(rec.get("usdt")),
        buy_rate=to_decimal(rec.get("buy_rate")),
        sell_rate=to_decimal(rec.get("sell_rate")),
        profit_pct=to_decimal(rec.get("profit")),
        receiver=str(rec.get("receiver") or ""),
        bank=str(rec.get("bank") or ""),
        last4=str(rec.get("last4") or ""),
        confidence=to_decimal(rec["confidence"]) if rec.get("confidence") is not None else None,
        status=PipelineStatus(rec.get("status") or PipelineStatus.WAITING_USDT.value)
        if rec.get("status") in {s.value for s in PipelineStatus}
        else PipelineStatus.WAITING_USDT,
        staff=rec.get("staff"),
    )
