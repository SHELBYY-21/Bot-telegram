"""Premium console cards — one card per message, one decision per screen.

Rendered as Telegram HTML. Numbers always go through <code> (monospace).
No paragraphs. Labels small. Values large. Terminal hierarchy.
"""

from __future__ import annotations

import html
from typing import Any, Mapping

from vault import PRODUCT_NAME, PRODUCT_SUBTITLE
from vault.formatting import coalesce, confidence, crypto, mask_account, money, pct, when
from vault.theme import OCR_WARN_THRESHOLD, PIPELINE, Status


HR = "────────────────────"
DOT_ON = "●"
DOT_OFF = "○"


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _mono(value: Any) -> str:
    return f"<code>{_e(value)}</code>"


def _label(text: str) -> str:
    return f"<i>{_e(text)}</i>"


def _header(ledger_id: str | None = None, subtitle: str | None = None) -> list[str]:
    lines = [
        f"<b>{_e(PRODUCT_NAME)}</b>",
        _mono(subtitle or PRODUCT_SUBTITLE),
    ]
    if ledger_id:
        lines.append(_mono(ledger_id))
    lines.append(HR)
    return lines


def status_rail(active: Status) -> list[str]:
    """Pipeline status rail — only the active step glows."""
    lines: list[str] = []
    for step in PIPELINE:
        if step == active:
            lines.append(f"<b>{DOT_ON} {_e(step.value)}</b>")
        else:
            # Past steps keep a filled but muted mark; future stay hollow.
            if active in PIPELINE and step.pipeline_index < active.pipeline_index:
                lines.append(f"{DOT_ON} {_e(step.value)}")
            else:
                lines.append(f"<code>{DOT_OFF} {_e(step.value)}</code>")
    return lines


def _kv(label: str, value: str, *, mono: bool = True) -> list[str]:
    rendered = _mono(value) if mono else f"<b>{_e(value)}</b>"
    return [_label(label), rendered, ""]


def receive_card(
    *,
    ledger_id: str,
    thb: float | None = None,
    usdt: float | None = None,
    buy_rate: float | None = None,
    sell_rate: float | None = None,
    profit: float | None = None,
    receiver: str | None = None,
    bank: str | None = None,
    last4: str | None = None,
    conf: float | None = None,
    status: Status = Status.RECEIVED,
) -> str:
    """Transaction / confirmation card — the primary decision screen."""
    lines = _header(ledger_id)
    lines.extend(status_rail(status))
    lines.append(HR)
    lines.append("")

    lines.extend(_kv("THB", money(thb)))
    lines.extend(_kv("USDT", crypto(usdt)))
    lines.extend(_kv("Buy Rate", money(buy_rate)))
    lines.extend(_kv("Sell Rate", money(sell_rate)))
    lines.extend(_kv("Profit", pct(profit)))

    recv = receiver or mask_account(last4, bank)
    lines.extend(_kv("Receiver", recv, mono=False))
    if conf is not None:
        lines.extend(_kv("Confidence", confidence(conf)))

    # Trim trailing blank
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def ocr_card(
    *,
    ledger_id: str,
    vision: float | None,
    receiver: str | None,
    bank: str | None,
    last4: str | None,
    amount: float | None,
    verified: bool = True,
    duplicate: bool = False,
    repeat_receiver: bool = False,
) -> str:
    lines = _header(ledger_id, subtitle="Vision Pass")
    lines.extend(status_rail(Status.OCR_VERIFIED if verified else Status.RECEIVED))
    lines.append(HR)
    lines.append("")

    lines.extend(_kv("Vision", confidence(vision)))
    lines.extend(_kv("Receiver", coalesce(receiver), mono=False))
    lines.extend(_kv("Bank", coalesce(bank)))
    lines.extend(_kv("Last4", coalesce(last4)))
    lines.extend(_kv("Detected Amount", money(amount)))
    status_label = "Verified" if verified else "Review"
    if vision is not None and vision < OCR_WARN_THRESHOLD:
        status_label = "Low Confidence"
    lines.extend(_kv("Status", status_label, mono=False))

    flags: list[str] = []
    if vision is not None and vision < OCR_WARN_THRESHOLD:
        flags.append("CONFIDENCE BELOW 90%")
    if duplicate:
        flags.append("DUPLICATE SLIP")
    if repeat_receiver:
        flags.append("REPEAT RECEIVER")
    if flags:
        lines.append(HR)
        for f in flags:
            lines.append(f"<b>! {_e(f)}</b>")

    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def history_card(
    *,
    bank: str | None,
    last4: str | None,
    name: str | None = None,
    tx_count: int = 0,
    total_thb: float = 0.0,
    total_usdt: float = 0.0,
    first_seen: str | None = None,
    last_seen: str | None = None,
    risk: str = "LOW",
) -> str:
    lines = _header(subtitle="Receiver History")
    lines.append("")
    lines.extend(_kv("Receiver", mask_account(last4, bank), mono=False))
    if name:
        lines.extend(_kv("Name", name, mono=False))
    lines.extend(_kv("Transactions", f"{tx_count:,}"))
    lines.extend(_kv("THB", money(total_thb)))
    lines.extend(_kv("USDT", crypto(total_usdt)))
    lines.extend(_kv("First Seen", when(first_seen), mono=False))
    lines.extend(_kv("Last Seen", when(last_seen), mono=False))
    risk_u = (risk or "LOW").upper()
    risk_line = f"<b>{_e(risk_u)}</b>" if risk_u != "LOW" else _mono(risk_u)
    lines.append(_label("Risk"))
    lines.append(risk_line)

    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def success_card(
    *,
    ledger_id: str,
    profit: float | None,
    balance_usdt: float | None = None,
    thb: float | None = None,
    usdt: float | None = None,
) -> str:
    lines = _header(ledger_id)
    lines.extend(status_rail(Status.SETTLED))
    lines.append(HR)
    lines.append("")
    lines.append("<b>● SETTLED</b>")
    lines.append("")
    lines.extend(_kv("Ledger ID", ledger_id))
    if thb is not None:
        lines.extend(_kv("THB", money(thb)))
    if usdt is not None:
        lines.extend(_kv("USDT", crypto(usdt)))
    lines.extend(_kv("Profit", pct(profit)))
    if balance_usdt is not None:
        lines.extend(_kv("Updated Balance", crypto(balance_usdt)))
    lines.append("")
    lines.append("<b>Done.</b>")

    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def error_card(*, problem: str, cause: str, action: str) -> str:
    lines = _header(subtitle="Exception")
    lines.append("")
    lines.extend(_kv("Problem", problem, mono=False))
    lines.extend(_kv("Cause", cause, mono=False))
    lines.extend(_kv("Action", action, mono=False))
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def edit_card(
    *,
    ledger_id: str,
    field: str,
    current: str,
    hint: str,
) -> str:
    lines = _header(ledger_id, subtitle="Edit Mode")
    lines.append("")
    lines.extend(_kv("Field", field, mono=False))
    lines.extend(_kv("Current", current))
    lines.append(_label("Input"))
    lines.append(_e(hint))
    return "\n".join(lines)


def delete_card(*, ledger_id: str, summary: str) -> str:
    lines = _header(ledger_id, subtitle="Delete")
    lines.append("")
    lines.extend(_kv("Target", ledger_id))
    lines.extend(_kv("Summary", summary, mono=False))
    lines.append("")
    lines.append("<i>This action is permanent.</i>")
    return "\n".join(lines)


def loading_card(*, stage: str = "Processing", progress: int | None = None) -> str:
    lines = _header(subtitle="Console")
    lines.append("")
    lines.append(f"<b>{_e(stage)}</b>")
    if progress is not None:
        filled = max(0, min(10, progress // 10))
        bar = "█" * filled + "░" * (10 - filled)
        lines.append(_mono(f"{bar} {progress}%"))
    else:
        lines.append(_mono("····"))
    return "\n".join(lines)


def welcome_card() -> str:
    lines = _header(subtitle=PRODUCT_SUBTITLE)
    lines.append("")
    lines.append(_label("Operations"))
    lines.append("Send a slip image")
    lines.append("or USDT amount")
    lines.append("")
    lines.append(_label("Commands"))
    lines.append(_mono("/rates"))
    lines.append(_mono("/balance"))
    lines.append(_mono("/history"))
    lines.append(_mono("/ledger <id>"))
    lines.append(_mono("/setrates <buy> <sell>"))
    return "\n".join(lines)


def rates_card(*, buy: float, sell: float, profit: float, balance: float | None = None) -> str:
    lines = _header(subtitle="Rate Desk")
    lines.append("")
    lines.extend(_kv("Buy Rate", money(buy)))
    lines.extend(_kv("Sell Rate", money(sell)))
    lines.extend(_kv("Spread", pct(profit)))
    if balance is not None:
        lines.extend(_kv("USDT Balance", crypto(balance)))
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def ledger_list_card(rows: list[Mapping[str, Any]]) -> str:
    lines = _header(subtitle="Ledger")
    lines.append("")
    if not rows:
        lines.append(_mono("No entries"))
        return "\n".join(lines)
    for row in rows:
        lid = row.get("id", "?")
        status = row.get("status", "?")
        thb = money(row.get("thb"))
        lines.append(f"{_mono(lid)}  {_e(status)}")
        lines.append(f"  {_mono(thb)} THB")
        lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)
