"""Design tokens and status pipeline for the OLED console aesthetic.

Telegram cannot render hex colors, so the visual language is expressed through
typography hierarchy, monospace figures, status glyphs, and whitespace.
"""

from __future__ import annotations

from enum import Enum

# Hex tokens — documented for clients / future web surfaces
PRIMARY = "#05050A"
SURFACE = "#101114"
BORDER = "rgba(255,255,255,.06)"
ACCENT_GOLD = "#E5C04A"
ACCENT_CYAN = "#00F0FF"
SUCCESS = "#00D26A"
WARNING = "#FFB800"
DANGER = "#FF4D4F"

RULE = "────────────────────────────"
RULE_WIDE = "────────────────────────────────"

# Status pipeline — only ONE active status glows
STATUS_ORDER = ("RECEIVED", "OCR_VERIFIED", "WAITING_USDT", "SETTLED")

STATUS_LABELS = {
    "RECEIVED": "RECEIVED",
    "OCR_VERIFIED": "OCR VERIFIED",
    "WAITING_USDT": "WAITING USDT",
    "SETTLED": "SETTLED",
    "CANCELLED": "CANCELLED",
    "ERROR": "ERROR",
    "EDITING": "EDITING",
    "DELETED": "DELETED",
}


class TxStatus(str, Enum):
    RECEIVED = "RECEIVED"
    OCR_VERIFIED = "OCR_VERIFIED"
    WAITING_USDT = "WAITING_USDT"
    SETTLED = "SETTLED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"
    EDITING = "EDITING"
    DELETED = "DELETED"


def status_pipeline(active: str | TxStatus) -> str:
    """Render the four-step pipeline with a single glowing active node."""
    active_key = active.value if isinstance(active, TxStatus) else str(active).upper()
    lines: list[str] = []
    in_pipeline = active_key in STATUS_ORDER
    for key in STATUS_ORDER:
        label = STATUS_LABELS[key]
        if in_pipeline and key == active_key:
            # Glowing node — filled bullet + bold label
            lines.append(f"● <b>{label}</b>")
        else:
            lines.append(f"○ {label}")
    if not in_pipeline and active_key in STATUS_LABELS:
        lines.append(f"● <b>{STATUS_LABELS[active_key]}</b>")
    return "\n".join(lines)


def confidence_tone(confidence: float) -> str:
    """Return WARN / OK label tone for OCR confidence."""
    if confidence < 90.0:
        return "WARN"
    return "OK"
