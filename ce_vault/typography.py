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
    # 32 chars — matches the CE VAULT OS card width from the mockups.
    return "────────────────────────────────"


def boxed_title(title: str, subtitle: str | None = None) -> str:
    """Rounded-corner box frame around a centered title.

    Rendered as three lines, matching the mockup:
        ╭──────────────────────────────╮
                 <title>
              <subtitle?>
        ╰──────────────────────────────╯

    Title is upper-cased (CE VAULT design language: headings = UPPERCASE).
    Uses <pre> so Telegram keeps the exact spacing.
    """
    width = 30
    top = "╭" + "─" * width + "╮"
    bot = "╰" + "─" * width + "╯"
    # Case is the author's call — mockups show both "CE VAULT" (upper) and
    # "Confirm Transaction" (Title Case) in the box.
    lines = [top, title.center(width)]
    if subtitle:
        lines.append(subtitle.center(width))
    lines.append(bot)
    return "<pre>" + esc("\n".join(lines)) + "</pre>"


BADGE_MAP = {
    "RECEIVED": "PROCESSING",
    "OCR VERIFIED": "VERIFIED",
    "WAITING USDT": "WAITING",
    "SETTLED": "SETTLED",
    "CANCELLED": "REVIEW",
    "ERROR": "ERROR",
    "EDITING": "REVIEW",
}


def status_badge(status: str, *, right: str | None = None) -> str:
    """Single ● BADGE pill (design: one badge per card).

    ``right`` puts an aligned right-hand value on the same line — used by the
    OCR VERIFIED card which pairs the badge with the confidence number.
    """
    label_text = BADGE_MAP.get((status or "").upper().replace("_", " "), status.upper())
    left = f"<b>● {esc(label_text)}</b>"
    if right is None:
        return left
    return f"{left}{' ' * 4}{mono(right)}"


def section(label_text: str, value: str, *, extra: str | None = None) -> str:
    """CE VAULT section block — small UPPERCASE label, blank line, mono value.

    ``extra`` renders on its own line beneath the primary value (e.g. the
    receiver name below the "SCB ••••3376" line, or the time below the date).
    """
    # Case is the author's call: card 1 uses UPPERCASE (AMOUNT, RECEIVER,
    # DATE, NEXT), other cards use Title Case (Buy Rate, First Seen). The
    # mockups mix both, so we pass through and let the card decide.
    lines = [label(label_text), "", mono(value)]
    if extra:
        lines.extend(["", esc(extra)])
    return "\n".join(lines)


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
