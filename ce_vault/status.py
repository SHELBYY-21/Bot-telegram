"""Pipeline status rendering — one active status glows."""

from __future__ import annotations

from enum import Enum

from ce_vault import theme as T


class PipelineStatus(str, Enum):
    RECEIVED = "RECEIVED"
    OCR_VERIFIED = "OCR VERIFIED"
    WAITING_USDT = "WAITING USDT"
    SETTLED = "SETTLED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


PIPELINE_ORDER = (
    PipelineStatus.RECEIVED,
    PipelineStatus.OCR_VERIFIED,
    PipelineStatus.WAITING_USDT,
    PipelineStatus.SETTLED,
)


def render_pipeline(active: PipelineStatus | str) -> str:
    """Status rail — only the active step glows (bold + filled bullet)."""
    active_status = PipelineStatus(active) if not isinstance(active, PipelineStatus) else active

    if active_status in (PipelineStatus.FAILED, PipelineStatus.CANCELLED):
        return f"● <b>{T.esc(active_status.value)}</b>"

    lines: list[str] = []
    for step in PIPELINE_ORDER:
        if step == active_status:
            lines.append(f"● <b>{T.esc(step.value)}</b>")
        else:
            lines.append(f"○ {T.esc(step.value)}")
    return "\n".join(lines)
