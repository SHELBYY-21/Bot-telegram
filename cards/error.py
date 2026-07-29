"""Error card."""

from __future__ import annotations

from cards.base import SEP, esc, header


def error_card(problem: str, cause: str, action: str) -> str:
    lines = [
        header(),
        "",
        "Problem",
        f"<b>{esc(problem)}</b>",
        "",
        "Cause",
        esc(cause),
        "",
        "Action",
        esc(action),
        SEP,
    ]
    return "\n".join(lines)
