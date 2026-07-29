"""Typography and layout primitives for CE VAULT cards.

Telegram cannot render CSS colors. Hierarchy is expressed through
monospace numbers, sparse labels, and exact vertical rhythm.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone


RULE = "━━━━━━━━━━━━━━━━━━━━"
THIN = "────────────────────"


def esc(value: object) -> str:
    return html.escape(str(value if value is not None else "—"))


def mono(value: object) -> str:
    """Monospace every money / crypto / ID value."""
    return f"<code>{esc(value)}</code>"


def label(text: str) -> str:
    return f"<i>{esc(text)}</i>"


def value_block(lbl: str, val: object, *, large: bool = False) -> str:
    rendered = mono(val)
    if large:
        rendered = f"<b>{rendered}</b>"
    return f"{label(lbl)}\n{rendered}"


def header(ledger_id: str | None = None, subtitle: str = "Secure Ledger") -> str:
    lines = [
        "<b>CE VAULT</b>",
        label(subtitle),
    ]
    if ledger_id:
        lines.append(mono(ledger_id))
    lines.append(RULE)
    return "\n".join(lines)


def footer_sep() -> str:
    return THIN


def fmt_thb(amount: float | None) -> str:
    if amount is None:
        return "—"
    return f"{amount:,.2f}"


def fmt_usdt(amount: float | None) -> str:
    if amount is None:
        return "—"
    return f"{amount:,.4f}"


def fmt_rate(rate: float | None) -> str:
    if rate is None:
        return "—"
    return f"{rate:,.2f}"


def fmt_pct(pct: float | None) -> str:
    if pct is None:
        return "—"
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


def fmt_confidence(pct: float | None) -> str:
    if pct is None:
        return "—"
    return f"{pct:.1f}%"


def fmt_day(iso_ts: str | None) -> str:
    if not iso_ts:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except ValueError:
        return iso_ts[:10]
    now = datetime.now(timezone.utc).date()
    if dt.date() == now:
        return "Today"
    return dt.strftime("%Y-%m-%d")


def progress_bar(ratio: float, width: int = 12) -> str:
    ratio = max(0.0, min(1.0, ratio))
    filled = int(round(ratio * width))
    return "█" * filled + "░" * (width - filled)
