"""Success card."""

from __future__ import annotations

from typing import Any

from cards.base import SEP, header, money, pct


def success_card(tx: dict[str, Any]) -> str:
    lines = [
        header(),
        "",
        "<b>SETTLED</b>",
        "",
        "Ledger ID",
        f"<code>{tx.get('id', '')}</code>",
        "",
        "Profit",
        pct(tx.get("profit_pct")),
        "",
        "Updated Balance",
        money(tx.get("_new_balance"), "USDT"),
        "",
        "Done.",
        SEP,
    ]
    return "\n".join(lines)
