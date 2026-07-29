"""Pipeline status indicators — one active glow at a time."""

from __future__ import annotations

from enum import Enum

from ce_vault.theme import esc


class PipelineStatus(str, Enum):
    RECEIVED = "RECEIVED"
    OCR_VERIFIED = "OCR VERIFIED"
    WAITING_USDT = "WAITING USDT"
    SETTLED = "SETTLED"
    ERROR = "ERROR"
    EDITING = "EDITING"
    DELETED = "DELETED"


PIPELINE_ORDER = [
    PipelineStatus.RECEIVED,
    PipelineStatus.OCR_VERIFIED,
    PipelineStatus.WAITING_USDT,
    PipelineStatus.SETTLED,
]


def render_pipeline(active: PipelineStatus) -> str:
    """Render status rail. Only the active step glows (bold ●)."""
    lines: list[str] = []
    for step in PIPELINE_ORDER:
        if step == active:
            lines.append(f"<b>● {esc(step.value)}</b>")
        elif _is_past(step, active):
            lines.append(f"● {esc(step.value)}")
        else:
            lines.append(f"○ {esc(step.value)}")
    return "\n".join(lines)


def _is_past(step: PipelineStatus, active: PipelineStatus) -> bool:
    if active not in PIPELINE_ORDER:
        return False
    return PIPELINE_ORDER.index(step) < PIPELINE_ORDER.index(active)


def render_single(status: PipelineStatus, *, glow: bool = True) -> str:
    if glow:
        return f"<b>● {esc(status.value)}</b>"
    return f"● {esc(status.value)}"
