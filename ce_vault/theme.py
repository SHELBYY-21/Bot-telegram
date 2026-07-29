"""Design tokens and typography helpers for CE Vault cards.

Visual language: dark OLED terminal — typography first, monospace numbers,
one card = one decision. Telegram HTML only (no CSS); spacing is intentional.
"""

from __future__ import annotations

import html
import re
from decimal import Decimal, ROUND_HALF_UP

# Palette (documentation / future WebApp — Telegram cannot paint backgrounds)
PRIMARY = "#05050A"
SURFACE = "#101114"
BORDER = "rgba(255,255,255,.06)"
GOLD = "#E5C04A"
CYAN = "#00F0FF"
SUCCESS = "#00D26A"
WARNING = "#FFB800"
DANGER = "#FF4D4F"

RULE = "────────────────────────"
RULE_SHORT = "────────────"


def esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def mono(value: object) -> str:
    """Monospace every number / code value."""
    return f"<code>{esc(value)}</code>"


def label(text: str) -> str:
    return f"<i>{esc(text)}</i>"


def title(text: str) -> str:
    return f"<b>{esc(text)}</b>"


def header(brand: str = "CE VAULT", subtitle: str = "Secure Ledger", ledger_id: str | None = None) -> str:
    lines = [
        title(brand),
        label(subtitle),
    ]
    if ledger_id:
        lines.append(mono(ledger_id))
    lines.append(RULE)
    return "\n".join(lines)


def field(name: str, value: object, *, code: bool = False) -> str:
    rendered = mono(value) if code else esc(value)
    return f"{label(name)}\n{rendered}"


def money(amount: Decimal | float | str | int, *, places: int = 2) -> str:
    d = _as_decimal(amount).quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP)
    return f"{d:,.{places}f}"


def crypto(amount: Decimal | float | str | int, *, places: int = 4) -> str:
    d = _as_decimal(amount).quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP)
    return f"{d:.{places}f}"


def pct(value: Decimal | float | str | int, *, places: int = 2, signed: bool = True) -> str:
    d = _as_decimal(value).quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP)
    if signed:
        return f"{d:+.{places}f}%"
    return f"{d:.{places}f}%"


def mask_account(last4: str | None, bank: str | None = None) -> str:
    digits = re.sub(r"\D", "", last4 or "")[-4:] or "????"
    bank_part = (bank or "BANK").upper().strip()
    return f"{bank_part} ••••{digits}"


def _as_decimal(value: Decimal | float | str | int) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
