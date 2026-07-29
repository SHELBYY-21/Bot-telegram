"""Design tokens and typography primitives for the CE VAULT console.

Telegram cannot render CSS, so the OLED palette is expressed through
spacing, monospace numbers, status glyphs, and strict card hierarchy.
"""

from __future__ import annotations

# Visual palette (documented for clients / future WebApp surfaces)
PRIMARY = "#05050A"
SURFACE = "#101114"
BORDER = "rgba(255,255,255,.06)"
ACCENT_GOLD = "#E5C04A"
ACCENT_CYAN = "#00F0FF"
SUCCESS = "#00D26A"
WARNING = "#FFB800"
DANGER = "#FF4D4F"

BRAND = "CE VAULT"
SUBTITLE = "Secure Ledger"

RULE = "────────────────────────"

# Pipeline statuses — only one may be active (glow = bold)
STATUSES = ("RECEIVED", "OCR VERIFIED", "WAITING USDT", "SETTLED")

STATUS_RECEIVED = "RECEIVED"
STATUS_OCR_VERIFIED = "OCR VERIFIED"
STATUS_WAITING_USDT = "WAITING USDT"
STATUS_SETTLED = "SETTLED"
STATUS_CANCELLED = "CANCELLED"
STATUS_ERROR = "ERROR"


def money(value: float | int | str, *, decimals: int = 2) -> str:
    """Format a monetary value for monospace display."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    if decimals == 0:
        return f"{n:,.0f}"
    return f"{n:,.{decimals}f}"


def crypto(value: float | int | str, *, decimals: int = 4) -> str:
    return money(value, decimals=decimals)


def pct(value: float | int | str, *, decimals: int = 2, signed: bool = True) -> str:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    if signed:
        return f"{n:+.{decimals}f}%"
    return f"{n:.{decimals}f}%"


def mask_account(last4: str | None, bank: str | None = None) -> str:
    digits = "".join(c for c in (last4 or "") if c.isdigit())[-4:]
    masked = f"••••{digits}" if digits else "••••————"
    if bank:
        return f"{bank} {masked}"
    return masked


def mono(value: str) -> str:
    """Wrap value in Telegram monospace (HTML)."""
    return f"<code>{value}</code>"


def label_value(label: str, value: str, *, mono_value: bool = False) -> str:
    rendered = mono(value) if mono_value else value
    return f"{label}\n{rendered}"


def header(ledger_id: str | None = None) -> str:
    lines = [
        f"<b>{BRAND}</b>",
        f"<i>{SUBTITLE}</i>",
    ]
    if ledger_id:
        lines.append(f"Ledger ID  {mono(ledger_id)}")
    lines.append(RULE)
    return "\n".join(lines)


def status_rail(active: str) -> str:
    """Render the status pipeline. Only the active step glows."""
    active_norm = active.upper().strip()
    lines = []
    for step in STATUSES:
        if step == active_norm:
            lines.append(f"<b>● {step}</b>")
        else:
            lines.append(f"○ {step}")
    return "\n".join(lines)


def field_block(rows: list[tuple[str, str, bool]]) -> str:
    """Render label/value rows. Each tuple: (label, value, use_mono)."""
    parts: list[str] = []
    for label, value, use_mono in rows:
        parts.append(label_value(label, value, mono_value=use_mono))
    return "\n\n".join(parts)
