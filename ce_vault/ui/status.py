"""Status rail — only one active stage glows."""

from __future__ import annotations

from ce_vault.config import STATUSES
from ce_vault.ui.theme import esc


def status_rail(active: str) -> str:
    """Render the four-stage ledger pipeline.

    Active stage: ● STAGE (bold)
    Idle stages:  ○ STAGE
    """
    active_norm = (active or "").upper().strip()
    lines: list[str] = []
    for stage in STATUSES:
        if stage == active_norm:
            lines.append(f"● <b>{esc(stage)}</b>")
        else:
            lines.append(f"○ {esc(stage)}")
    return "\n".join(lines)
