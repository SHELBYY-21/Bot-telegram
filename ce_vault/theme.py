"""Design tokens and typography helpers for the CE VAULT console.

Telegram cannot render CSS. These tokens drive consistent HTML layout:
monospace numbers, tight hierarchy, and terminal-grade spacing.
"""

from __future__ import annotations

import html
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

# Visual palette (documented for clients / future WebApp surfaces)
PRIMARY = "#05050A"
SURFACE = "#101114"
BORDER = "rgba(255,255,255,.06)"
ACCENT_GOLD = "#E5C04A"
ACCENT_CYAN = "#00F0FF"
SUCCESS = "#00D26A"
WARNING = "#FFB800"
DANGER = "#FF4D4F"

RULE = "────────────────"
THIN_RULE = "···············"

CONFIDENCE_WARN_THRESHOLD = Decimal("90.0")


def esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def money(value: Decimal | float | int | str | None, places: int = 2) -> str:
    """Format fiat/crypto amounts for monospace display."""
    d = to_decimal(value)
    quant = Decimal(10) ** -places
    return f"{d.quantize(quant, rounding=ROUND_HALF_UP):,.{places}f}"


def money_code(value: Decimal | float | int | str | None, places: int = 2) -> str:
    return f"<code>{esc(money(value, places))}</code>"


def pct(value: Decimal | float | int | str | None, places: int = 2) -> str:
    d = to_decimal(value)
    quant = Decimal(10) ** -places
    signed = d.quantize(quant, rounding=ROUND_HALF_UP)
    prefix = "+" if signed > 0 else ""
    return f"{prefix}{signed:.{places}f}%"


def pct_code(value: Decimal | float | int | str | None, places: int = 2) -> str:
    return f"<code>{esc(pct(value, places))}</code>"


def to_decimal(value: Decimal | float | int | str | None) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return Decimal("0")


def label_value(label: str, value: str) -> str:
    return f"<b>{esc(label)}</b>\n{value}"


def field(label: str, value: str) -> str:
    """Small label over large value — typography-first row."""
    return f"{esc(label)}\n{value}"


def header(ledger_id: str | None = None, subtitle: str = "Secure Ledger") -> str:
    lines = [
        "<b>CE VAULT</b>",
        f"<i>{esc(subtitle)}</i>",
    ]
    if ledger_id:
        lines.append(f"Ledger ID  <code>{esc(ledger_id)}</code>")
    lines.append(RULE)
    return "\n".join(lines)


def mask_account(last4: str | None, bank: str | None = None) -> str:
    digits = re.sub(r"\D", "", last4 or "")[-4:] or "····"
    bank_part = (bank or "BANK").upper()
    return f"{esc(bank_part)} ••••{esc(digits)}"


def truncate(text: str, max_len: int = 28) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"
