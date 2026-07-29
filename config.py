"""CE VAULT configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    allowed_user_ids: frozenset[int]
    database_path: Path
    state_file: Path
    default_buy_rate: float
    default_sell_rate: float
    ocr_provider: str
    google_vision_api_key: str | None
    low_confidence_threshold: float
    staff_name: str

    @classmethod
    def from_env(cls) -> Settings:
        raw_ids = os.environ.get("ALLOWED_USER_IDS", "").strip()
        allowed = (
            frozenset(int(x) for x in raw_ids.replace(",", " ").split() if x)
            if raw_ids
            else frozenset()
        )
        return cls(
            telegram_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            allowed_user_ids=allowed,
            database_path=Path(os.environ.get("DATABASE_PATH", "vault.db")),
            state_file=Path(os.environ.get("STATE_FILE", "state.json")),
            default_buy_rate=float(os.environ.get("DEFAULT_BUY_RATE", "39.89")),
            default_sell_rate=float(os.environ.get("DEFAULT_SELL_RATE", "40.00")),
            ocr_provider=os.environ.get("OCR_PROVIDER", "mock").lower(),
            google_vision_api_key=os.environ.get("GOOGLE_VISION_API_KEY"),
            low_confidence_threshold=float(os.environ.get("LOW_CONFIDENCE_THRESHOLD", "90")),
            staff_name=os.environ.get("STAFF_NAME", "Operator"),
        )


def load_settings() -> Settings:
    settings = Settings.from_env()
    if not settings.telegram_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN must be set")
    return settings
