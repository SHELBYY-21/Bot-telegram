"""Transaction status pipeline — one active status glows."""

from __future__ import annotations

from ce_vault.config import STATUS_PIPELINE
from ce_vault.typography import esc


ACTIVE_GLYPH = "●"
IDLE_GLYPH = "○"


def normalize_status(status: str | None) -> str:
    if not status:
        return STATUS_PIPELINE[0]
    key = status.strip().upper().replace("_", " ")
    aliases = {
        "RECEIVED": "RECEIVED",
        "OCR": "OCR VERIFIED",
        "OCR VERIFIED": "OCR VERIFIED",
        "VERIFIED": "OCR VERIFIED",
        "WAITING": "WAITING USDT",
        "WAITING USDT": "WAITING USDT",
        "PENDING USDT": "WAITING USDT",
        "SETTLED": "SETTLED",
        "DONE": "SETTLED",
        "SUCCESS": "SETTLED",
        "CONFIRMED": "WAITING USDT",
    }
    return aliases.get(key, key if key in STATUS_PIPELINE else STATUS_PIPELINE[0])


def render_status_rail(active: str | None) -> str:
    """Render pipeline; only the active step glows (bold)."""
    current = normalize_status(active)
    lines: list[str] = []
    for step in STATUS_PIPELINE:
        if step == current:
            lines.append(f"<b>{ACTIVE_GLYPH} {esc(step)}</b>")
        else:
            lines.append(f"{IDLE_GLYPH} {esc(step)}")
    return "\n".join(lines)


def next_status(current: str | None) -> str | None:
    cur = normalize_status(current)
    try:
        idx = STATUS_PIPELINE.index(cur)
    except ValueError:
        return None
    if idx + 1 >= len(STATUS_PIPELINE):
        return None
    return STATUS_PIPELINE[idx + 1]
