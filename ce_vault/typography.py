"""Typography and number formatting — monospace for every monetary value."""

from __future__ import annotations

import html
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _d(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def money(value: Any, places: int = 2) -> str:
    """Format fiat/crypto amounts for monospace display."""
    q = Decimal("1").scaleb(-places)
    n = _d(value).quantize(q, rounding=ROUND_HALF_UP)
    return f"{n:,.{places}f}"


def money_signed(value: Any, places: int = 2) -> str:
    n = _d(value)
    sign = "+" if n >= 0 else ""
    return f"{sign}{money(n, places)}"


def pct(value: Any, places: int = 2) -> str:
    n = _d(value)
    sign = "+" if n >= 0 else ""
    q = Decimal("1").scaleb(-places)
    return f"{sign}{n.quantize(q, rounding=ROUND_HALF_UP):.{places}f}%"


def mono(value: Any) -> str:
    return f"<code>{esc(value)}</code>"


def label(text: str) -> str:
    return f"<i>{esc(text)}</i>"


def value_row(lbl: str, val: str, *, monospace: bool = True) -> str:
    rendered = mono(val) if monospace else esc(val)
    return f"{label(lbl)}\n{rendered}"


def divider() -> str:
    return "────────────────────"


def mask_account(last4: str | None) -> str:
    digits = "".join(c for c in (last4 or "") if c.isdigit())[-4:]
    if not digits:
        return "————"
    return f"••••{digits}"


def bank_receiver(bank: str | None, last4: str | None) -> str:
    b = (bank or "BANK").strip().upper() or "BANK"
    return f"{b} {mask_account(last4)}"


def format_ts(ts: str | datetime | None) -> str:
    if ts is None:
        return "—"
    if isinstance(ts, datetime):
        dt = ts
    else:
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            return esc(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone()
    today = datetime.now(timezone.utc).astimezone().date()
    if local.date() == today:
        return "Today"
    return local.strftime("%Y-%m-%d")


def relative_or_date(ts: str | datetime | None) -> str:
    return format_ts(ts)


def risk_level(tx_count: int, total_thb: float) -> str:
    if tx_count >= 40 or total_thb >= 2_000_000:
        return "HIGH"
    if tx_count >= 15 or total_thb >= 500_000:
        return "MED"
    return "LOW"
