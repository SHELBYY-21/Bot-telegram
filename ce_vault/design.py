"""Design tokens and status vocabulary for CE VAULT.

Telegram cannot render hex colors, so the palette is encoded as
typography + monospace + status glyphs. Tokens remain the single
source of truth for docs, Mini App, and future clients.
"""

from __future__ import annotations

from enum import Enum

# --- Palette (OLED console) ----------------------------------------------

PRIMARY = "#05050A"
SURFACE = "#101114"
BORDER = "rgba(255,255,255,.06)"
ACCENT_GOLD = "#E5C04A"
ACCENT_CYAN = "#00F0FF"
SUCCESS = "#00D26A"
WARNING = "#FFB800"
DANGER = "#FF4D4F"

BRAND = "CE VAULT"
SUBTITLE = "Secure Ledger"

# --- Status pipeline -----------------------------------------------------


class LedgerStatus(str, Enum):
    RECEIVED = "RECEIVED"
    OCR_VERIFIED = "OCR VERIFIED"
    WAITING_USDT = "WAITING USDT"
    SETTLED = "SETTLED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


# Ordered pipeline shown on cards. Only the active step glows (● vs ○).
STATUS_PIPELINE: tuple[LedgerStatus, ...] = (
    LedgerStatus.RECEIVED,
    LedgerStatus.OCR_VERIFIED,
    LedgerStatus.WAITING_USDT,
    LedgerStatus.SETTLED,
)


class AgentStatus(str, Enum):
    """Cursor agent lifecycle mapped to console vocabulary."""

    QUEUED = "QUEUED"
    CREATING = "CREATING"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    ERROR = "ERROR"
    STOPPED = "STOPPED"


AGENT_PIPELINE: tuple[str, ...] = ("QUEUED", "CREATING", "RUNNING", "FINISHED")

# Map Cursor API statuses → console labels
AGENT_STATUS_MAP: dict[str, str] = {
    "CREATING": "QUEUED",
    "PENDING": "QUEUED",
    "QUEUED": "QUEUED",
    "RUNNING": "RUNNING",
    "FINISHED": "FINISHED",
    "COMPLETED": "FINISHED",
    "ERROR": "ERROR",
    "FAILED": "ERROR",
    "EXPIRED": "ERROR",
    "STOPPED": "STOPPED",
    "CANCELLED": "STOPPED",
}

CONFIDENCE_WARN_BELOW = 90.0
