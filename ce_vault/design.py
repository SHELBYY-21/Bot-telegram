"""Design tokens and visual language for CE VAULT.

Telegram cannot render CSS colors, but hierarchy, monospace numbers,
status glow, and card density follow the OLED console language.
"""

from __future__ import annotations

# --- Palette (reference — hierarchy encoded in typography) ---
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

RULE = "────────────────"

# Pipeline — only one status glows (bold) at a time
STATUSES = ("RECEIVED", "OCR VERIFIED", "WAITING USDT", "SETTLED")

STATUS_RECEIVED = "RECEIVED"
STATUS_OCR = "OCR VERIFIED"
STATUS_WAITING = "WAITING USDT"
STATUS_SETTLED = "SETTLED"

CONFIDENCE_WARN = 90.0
