"""Design tokens for the CE VAULT console.

Telegram HTML cannot paint true hex colors, so we encode the brand
language through typography, monospace numbers, status glyphs, and
spacing — the visual system still maps to these tokens.
"""

from __future__ import annotations

from enum import Enum


class Color:
    PRIMARY = "#05050A"
    SURFACE = "#101114"
    BORDER = "rgba(255,255,255,.06)"
    GOLD = "#E5C04A"
    CYAN = "#00F0FF"
    SUCCESS = "#00D26A"
    WARNING = "#FFB800"
    DANGER = "#FF4D4F"


class Status(str, Enum):
    RECEIVED = "RECEIVED"
    OCR_VERIFIED = "OCR VERIFIED"
    WAITING_USDT = "WAITING USDT"
    SETTLED = "SETTLED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"
    EDITING = "EDITING"

    @property
    def pipeline_index(self) -> int:
        order = [
            Status.RECEIVED,
            Status.OCR_VERIFIED,
            Status.WAITING_USDT,
            Status.SETTLED,
        ]
        try:
            return order.index(self)
        except ValueError:
            return -1


PIPELINE = (
    Status.RECEIVED,
    Status.OCR_VERIFIED,
    Status.WAITING_USDT,
    Status.SETTLED,
)

# Confidence below this triggers a warning on OCR cards.
OCR_WARN_THRESHOLD = 90.0

# Repeated receiver within this many hours elevates risk notice.
RECEIVER_REPEAT_HOURS = 24
