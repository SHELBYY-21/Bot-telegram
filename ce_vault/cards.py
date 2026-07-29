"""Premium single-card renderers for CE VAULT.

Every response is ONE card. Numbers are monospace. Labels are small.
No paragraphs. No emoji spam.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone

from ce_vault.design import BRAND, RULE, STATUSES, SUBTITLE
from ce_vault.models import OCRResult, ReceiverHistory, Transaction


def _e(value: object) -> str:
    return html.escape(str(value))


def _num(value: float | int | str, decimals: int | None = None) -> str:
    if isinstance(value, (int, float)) and decimals is not None:
        text = f"{value:,.{decimals}f}"
    elif isinstance(value, float):
        text = f"{value:,.4f}".rstrip("0").rstrip(".")
        if "." not in text:
            text = f"{value:,.2f}"
    else:
        text = str(value)
    return f"<code>{_e(text)}</code>"


def _money_thb(value: float) -> str:
    return f"<code>{_e(f'{value:,.2f}')}</code>"


def _money_usdt(value: float) -> str:
    return f"<code>{_e(f'{value:,.4f}')}</code>"


def _pct(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"<code>{_e(f'{sign}{value:.2f}%')}</code>"


def _field(label: str, value: str) -> str:
    return f"<b>{_e(label)}</b>\n{value}"


def header(ledger_id: str = "", subtitle: str = SUBTITLE) -> str:
    lines = [
        f"<b>{_e(BRAND)}</b>",
        f"<i>{_e(subtitle)}</i>",
    ]
    if ledger_id:
        lines.append(f"<code>{_e(ledger_id)}</code>")
    lines.append(RULE)
    return "\n".join(lines)


# Backward-compatible alias
_header = header


def _status_rail(active: str) -> str:
    rows = []
    for name in STATUSES:
        if name == active:
            rows.append(f"<b>● {_e(name)}</b>")
        else:
            rows.append(f"○ {_e(name)}")
    return "\n".join(rows)


def _today_label(iso: str) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso[:10]
    now = datetime.now(timezone.utc)
    if dt.date() == now.date():
        return "Today"
    return dt.strftime("%Y-%m-%d")


# --- Cards -----------------------------------------------------------------


def receive_card(ledger_id: str, progress: str = "Ingesting slip…") -> str:
    return "\n".join(
        [
            _header(ledger_id),
            "",
            _field("Channel", "Slip Intake"),
            "",
            _field("Progress", _e(progress)),
            "",
            _status_rail("RECEIVED"),
        ]
    )


def ocr_card(ledger_id: str, ocr: OCRResult, warn: bool = False) -> str:
    status_label = "Verified" if ocr.verified and not warn else ("Low Confidence" if warn else "Verified")
    name = ocr.receiver_name or "—"
    if len(name) > 24:
        name = name[:21] + "…"
    blocks = [
        _header(ledger_id),
        "",
        _field("Vision", _pct(ocr.confidence).replace("+", "")),
        "",
        _field("Receiver", _e(name)),
        "",
        _field("Bank", _e(ocr.bank or "—")),
        "",
        _field("Last4", f"<code>{_e(ocr.last4 or '————')}</code>"),
        "",
        _field("Detected Amount", _money_thb(ocr.amount_thb)),
        "",
        _field("Status", _e(status_label)),
    ]
    if ocr.duplicate:
        blocks.extend(["", _field("Alert", "Duplicate slip detected")])
    if warn:
        blocks.extend(["", _field("Alert", "Confidence below 90%")])
    if ocr.warning and not warn:
        blocks.extend(["", _field("Alert", _e(ocr.warning))])
    blocks.extend(["", _status_rail("OCR VERIFIED")])
    return "\n".join(blocks)


def confirmation_card(tx: Transaction) -> str:
    return "\n".join(
        [
            _header(tx.ledger_id),
            "",
            _field("THB", _money_thb(tx.thb)),
            "",
            _field("USDT", _money_usdt(tx.usdt)),
            "",
            _field("Buy Rate", _num(tx.buy_rate, 2)),
            "",
            _field("Sell Rate", _num(tx.sell_rate, 2)),
            "",
            _field("Profit", _pct(tx.profit_pct)),
            "",
            _field("Receiver", _e(tx.receiver_mask())),
            "",
            _field("Confidence", _pct(tx.confidence).replace("+", "")),
            "",
            RULE,
            "",
            _status_rail(tx.status if tx.status in STATUSES else "WAITING USDT"),
        ]
    )


def success_card(
    ledger_id: str,
    profit_pct: float,
    balance_usdt: float,
    profit_thb: float | None = None,
) -> str:
    lines = [
        _header(ledger_id, subtitle="Settlement Complete"),
        "",
        "<b>● SETTLED</b>",
        "",
        _field("Ledger ID", f"<code>{_e(ledger_id)}</code>"),
        "",
        _field("Profit", _pct(profit_pct)),
    ]
    if profit_thb is not None:
        lines.extend(["", _field("Profit THB", _money_thb(profit_thb))])
    lines.extend(
        [
            "",
            _field("Updated Balance", _money_usdt(balance_usdt) + " USDT"),
            "",
            "<i>Done.</i>",
        ]
    )
    return "\n".join(lines)


def history_card(hist: ReceiverHistory) -> str:
    return "\n".join(
        [
            _header(subtitle="Receiver History"),
            "",
            _field("Receiver", _e(hist.receiver_mask())),
            "",
            _field("Activity", f"<code>{hist.tx_count}</code> Transactions"),
            "",
            _field("Volume THB", _money_thb(hist.total_thb)),
            "",
            _field("Volume USDT", _money_usdt(hist.total_usdt)),
            "",
            _field("First Seen", _e(_today_label(hist.first_seen))),
            "",
            _field("Last Seen", _e(_today_label(hist.last_seen))),
            "",
            _field("Risk", f"<b>{_e(hist.risk)}</b>"),
        ]
    )


def error_card(problem: str, cause: str, action: str, ledger_id: str = "") -> str:
    return "\n".join(
        [
            _header(ledger_id, subtitle="Exception"),
            "",
            _field("Problem", _e(problem)),
            "",
            _field("Cause", _e(cause)),
            "",
            _field("Action", _e(action)),
        ]
    )


def edit_card(tx: Transaction, hint: str = "Send corrected USDT amount") -> str:
    return "\n".join(
        [
            _header(tx.ledger_id, subtitle="Edit Entry"),
            "",
            _field("THB", _money_thb(tx.thb)),
            "",
            _field("USDT", _money_usdt(tx.usdt)),
            "",
            _field("Receiver", _e(tx.receiver_mask())),
            "",
            _field("Instruction", _e(hint)),
            "",
            RULE,
            "",
            _status_rail(tx.status if tx.status in STATUSES else "WAITING USDT"),
        ]
    )


def delete_card(ledger_id: str, receiver: str = "") -> str:
    lines = [
        _header(ledger_id, subtitle="Void Entry"),
        "",
        _field("Ledger ID", f"<code>{_e(ledger_id)}</code>"),
    ]
    if receiver:
        lines.extend(["", _field("Receiver", _e(receiver))])
    lines.extend(
        [
            "",
            _field("State", "Pending void confirmation"),
            "",
            "<i>This action is irreversible.</i>",
        ]
    )
    return "\n".join(lines)


def loading_card(ledger_id: str, label: str = "Processing") -> str:
    return "\n".join(
        [
            _header(ledger_id),
            "",
            _field("State", f"<code>{_e(label)}</code>"),
            "",
            "▌",
            "",
            _status_rail("RECEIVED"),
        ]
    )


def console_home(balance_usdt: float, open_count: int, settled_today: int) -> str:
    return "\n".join(
        [
            _header(subtitle="Operations Console"),
            "",
            _field("Vault Balance", _money_usdt(balance_usdt) + " USDT"),
            "",
            _field("Open Ledgers", f"<code>{open_count}</code>"),
            "",
            _field("Settled Today", f"<code>{settled_today}</code>"),
            "",
            RULE,
            "",
            "<i>Send a slip image — or a USDT amount.</i>",
        ]
    )
