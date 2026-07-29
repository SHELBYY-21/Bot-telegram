"""Runtime configuration and design tokens."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


# --- Visual tokens (referenced in docs / future image cards) ---------------

class Theme:
    PRIMARY = "#05050A"
    SURFACE = "#101114"
    BORDER = "rgba(255,255,255,.06)"
    GOLD = "#E5C04A"
    CYAN = "#00F0FF"
    SUCCESS = "#00D26A"
    WARNING = "#FFB800"
    DANGER = "#FF4D4F"


# --- Status machine --------------------------------------------------------

STATUSES = ("RECEIVED", "OCR VERIFIED", "WAITING USDT", "SETTLED")
STATUS_RECEIVED = "RECEIVED"
STATUS_OCR = "OCR VERIFIED"
STATUS_WAITING = "WAITING USDT"
STATUS_SETTLED = "SETTLED"

CONFIDENCE_WARN_THRESHOLD = 90.0


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    allowed_user_ids: frozenset[int]
    db_path: Path
    images_dir: Path
    buy_rate: float
    sell_rate: float
    ocr_provider: str  # auto | openai | heuristic | none
    openai_api_key: str | None
    default_staff: str

    @classmethod
    def from_env(cls) -> Settings:
        raw_ids = os.environ.get("ALLOWED_USER_IDS", "").strip()
        allowed = (
            frozenset(int(x) for x in raw_ids.replace(",", " ").split() if x)
            if raw_ids
            else frozenset()
        )
        data_dir = Path(os.environ.get("DATA_DIR", "data"))
        return cls(
            telegram_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            allowed_user_ids=allowed,
            db_path=Path(os.environ.get("LEDGER_DB", str(data_dir / "ledger.db"))),
            images_dir=Path(os.environ.get("IMAGES_DIR", str(data_dir / "images"))),
            buy_rate=float(os.environ.get("BUY_RATE", "39.89")),
            sell_rate=float(os.environ.get("SELL_RATE", "40.00")),
            ocr_provider=os.environ.get("OCR_PROVIDER", "auto").lower(),
            openai_api_key=os.environ.get("OPENAI_API_KEY") or None,
            default_staff=os.environ.get("DEFAULT_STAFF", "ops"),
        )


def load_settings() -> Settings:
    return Settings.from_env()
