"""History card."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from cards.base import SEP, esc, header, money, receiver_display


def _format_date(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        today = datetime.now(dt.tzinfo).date()
        if dt.date() == today:
            return "Today"
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return esc(iso)


def history_card(receiver: dict[str, Any], risk: str = "LOW") -> str:
    lines = [
        header(),
        "",
        "Receiver",
        receiver_display(receiver.get("bank"), receiver.get("last4")),
        "",
        f"{receiver.get('tx_count', 0)} Transactions",
        "",
        money(receiver.get("total_thb", 0), "THB"),
        money(receiver.get("total_usdt", 0), "USDT"),
        "",
        "First Seen",
        esc(_format_date(receiver.get("first_seen"))),
        "",
        "Last Seen",
        esc(_format_date(receiver.get("last_seen"))),
        "",
        "Risk",
        f"<b>{esc(risk)}</b>",
        SEP,
    ]
    return "\n".join(lines)
