"""Runtime configuration and design tokens for CE VAULT."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


# --- Visual tokens (documented for product consistency; Telegram renders via typography) ---
class Palette:
    PRIMARY = "#05050A"
    SURFACE = "#101114"
    BORDER = "rgba(255,255,255,.06)"
    GOLD = "#E5C04A"
    CYAN = "#00F0FF"
    SUCCESS = "#00D26A"
    WARNING = "#FFB800"
    DANGER = "#FF4D4F"


BRAND = "CE VAULT"
SUBTITLE = "Secure Ledger"

STATUS_PIPELINE = (
    "RECEIVED",
    "OCR VERIFIED",
    "WAITING USDT",
    "SETTLED",
)


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return float(raw)


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    allowed_user_ids: frozenset[int]
    db_path: Path
    state_file: Path
    buy_rate: float
    sell_rate: float
    openai_api_key: str | None
    openai_base_url: str
    openai_vision_model: str
    ocr_warn_below: float
    images_dir: Path

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise SystemExit("TELEGRAM_BOT_TOKEN must be set")

        raw_ids = os.environ.get("ALLOWED_USER_IDS", "").strip()
        allowed = (
            frozenset(int(x) for x in raw_ids.replace(",", " ").split() if x)
            if raw_ids
            else frozenset()
        )

        db = Path(os.environ.get("LEDGER_DB", "data/ledger.db"))
        images = Path(os.environ.get("IMAGES_DIR", "data/slips"))
        state = Path(os.environ.get("STATE_FILE", "state.json"))

        buy = _float_env("BUY_RATE", 39.89)
        sell = _float_env("SELL_RATE", 40.00)
        if sell <= 0 or buy <= 0:
            raise SystemExit("BUY_RATE and SELL_RATE must be positive")

        return cls(
            telegram_token=token,
            allowed_user_ids=allowed,
            db_path=db,
            state_file=state,
            buy_rate=buy,
            sell_rate=sell,
            openai_api_key=os.environ.get("OPENAI_API_KEY") or None,
            openai_base_url=os.environ.get(
                "OPENAI_BASE_URL", "https://api.openai.com/v1"
            ).rstrip("/"),
            openai_vision_model=os.environ.get(
                "OPENAI_VISION_MODEL", "gpt-4o-mini"
            ),
            ocr_warn_below=_float_env("OCR_WARN_BELOW", 90.0),
            images_dir=images,
        )
