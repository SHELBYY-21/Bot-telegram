"""CE VAULT visual theme and formatting helpers."""

from __future__ import annotations

import html
from datetime import datetime

# Design tokens (reference for web surfaces; Telegram uses structured text)
COLORS = {
    "primary": "#05050A",
    "surface": "#101114",
    "border": "rgba(255,255,255,.06)",
    "accent_gold": "#E5C04A",
    "accent_cyan": "#00F0FF",
    "success": "#00D26A",
    "warning": "#FFB800",
    "danger": "#FF4D4F",
}

STATUS_ORDER = ("RECEIVED", "OCR_VERIFIED", "WAITING_USDT", "SETTLED")
STATUS_LABELS = {
    "RECEIVED": "RECEIVED",
    "OCR_VERIFIED": "OCR VERIFIED",
    "WAITING_USDT": "WAITING USDT",
    "SETTLED": "SETTLED",
}


def esc(value: object) -> str:
    return html.escape(str(value))


def mono(value: object) -> str:
    return f"<code>{esc(value)}</code>"


def divider() -> str:
    return "────────────────"


def header(ledger_id: str | None = None) -> str:
    lines = [
        "<b>CE VAULT</b>",
        "<i>Secure Ledger</i>",
    ]
    if ledger_id:
        lines.append(f"Ledger ID  {mono(ledger_id)}")
    lines.append(divider())
    return "\n".join(lines)


def status_pipeline(active: str) -> str:
    lines: list[str] = []
    for key in STATUS_ORDER:
        label = STATUS_LABELS[key]
        if key == active:
            lines.append(f"<b>● {esc(label)}</b>")
        else:
            lines.append(f"○ {esc(label)}")
    return "\n".join(lines)


def format_thb(value: float) -> str:
    return f"{value:,.2f}"


def format_usdt(value: float) -> str:
    return f"{value:,.4f}"


def format_pct(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def format_date(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        today = datetime.now(dt.tzinfo).date()
        if dt.date() == today:
            return "Today"
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return value[:10] if len(value) >= 10 else value
