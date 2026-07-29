"""CE VAULT configuration."""

from __future__ import annotations

import os
from pathlib import Path

# Paths
DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
DB_PATH = Path(os.environ.get("DB_PATH", str(DATA_DIR / "vault.db")))
STATE_FILE = Path(os.environ.get("STATE_FILE", "state.json"))
SLIPS_DIR = DATA_DIR / "slips"

# Rates (auto-applied — never ask user)
DEFAULT_BUY_RATE = float(os.environ.get("DEFAULT_BUY_RATE", "39.89"))
DEFAULT_SELL_RATE = float(os.environ.get("DEFAULT_SELL_RATE", "40.00"))

# OCR
OCR_CONFIDENCE_WARN = float(os.environ.get("OCR_CONFIDENCE_WARN", "90.0"))
OCR_API_URL = os.environ.get("OCR_API_URL", "").strip()

# Telegram
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USER_IDS_RAW = os.environ.get("ALLOWED_USER_IDS", "")

# Legacy Cursor API (backward compatibility)
CURSOR_API_KEY = os.environ.get("CURSOR_API_KEY", "")

# Status pipeline
STATUS_RECEIVED = "RECEIVED"
STATUS_OCR_VERIFIED = "OCR_VERIFIED"
STATUS_WAITING_USDT = "WAITING_USDT"
STATUS_SETTLED = "SETTLED"
STATUS_CANCELLED = "CANCELLED"

STATUS_PIPELINE = [
    STATUS_RECEIVED,
    STATUS_OCR_VERIFIED,
    STATUS_WAITING_USDT,
    STATUS_SETTLED,
]
