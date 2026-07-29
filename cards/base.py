"""Premium card formatters for CE VAULT."""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any

from config import STATUS_PIPELINE

# Visual constants (Telegram HTML)
SEP = "────────────────"
GLOW = "◉"
DOT = "●"
WARN = "▲"


def esc(value: Any) -> str:
    return html.escape(str(value)) if value is not None else ""


def mono(value: Any) -> str:
    return f"<code>{esc(value)}</code>"


def money(value: float | None, currency: str = "") -> str:
    if value is None:
        return mono("—")
    if currency == "THB":
        return mono(f"{value:,.2f}")
    if currency == "USDT":
        return mono(f"{value:,.4f}")
    return mono(f"{value:,.2f}")


def pct(value: float | None) -> str:
    if value is None:
        return mono("—")
    sign = "+" if value >= 0 else ""
    return mono(f"{sign}{value:.2f}%")


def header(ledger_id: str | None = None) -> str:
    lines = [
        "<b>CE VAULT</b>",
        "<i>Secure Ledger</i>",
    ]
    if ledger_id:
        lines.append(f"Ledger ID  {mono(ledger_id)}")
    lines.append(SEP)
    return "\n".join(lines)


def status_line(current: str) -> str:
    labels = {
        "RECEIVED": "RECEIVED",
        "OCR_VERIFIED": "OCR VERIFIED",
        "WAITING_USDT": "WAITING USDT",
        "SETTLED": "SETTLED",
    }
    lines = []
    for s in STATUS_PIPELINE:
        label = labels.get(s, s)
        if s == current:
            lines.append(f"{GLOW} <b>{label}</b>")
        else:
            idx_current = STATUS_PIPELINE.index(current) if current in STATUS_PIPELINE else -1
            idx_s = STATUS_PIPELINE.index(s)
            if idx_s < idx_current:
                lines.append(f"{DOT} {label}")
            else:
                lines.append(f"  {label}")
    return "\n".join(lines)


def field(label: str, value: str) -> str:
    return f"{label}\n{value}"


def pair_row(left_label: str, left_val: str, right_label: str, right_val: str) -> str:
    return f"{left_label}  {left_val}    {right_label}  {right_val}"


def receiver_display(bank: str | None, last4: str | None) -> str:
    if bank and last4:
        return f"{esc(bank)} ••••{esc(last4)}"
    return "—"
