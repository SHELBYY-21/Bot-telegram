"""Runtime configuration for CE Vault."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _f(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _b(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    allowed_user_ids: frozenset[int]
    db_path: Path
    buy_rate: float
    sell_rate: float
    ocr_warn_below: float
    openai_api_key: str | None
    ocr_model: str
    brand: str = "CE VAULT"
    subtitle: str = "Secure Ledger"


def load_settings() -> Settings:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN must be set")

    raw_ids = os.environ.get("ALLOWED_USER_IDS", "").strip()
    allowed = (
        frozenset(int(x) for x in raw_ids.replace(",", " ").split() if x)
        if raw_ids
        else frozenset()
    )

    return Settings(
        telegram_token=token,
        allowed_user_ids=allowed,
        db_path=Path(os.environ.get("LEDGER_DB", "ce_vault.db")),
        buy_rate=_f("BUY_RATE", 39.89),
        sell_rate=_f("SELL_RATE", 40.00),
        ocr_warn_below=_f("OCR_WARN_BELOW", 90.0),
        openai_api_key=os.environ.get("OPENAI_API_KEY") or None,
        ocr_model=os.environ.get("OCR_MODEL", "gpt-4o-mini"),
    )


def is_authorized(user_id: int | None, settings: Settings) -> bool:
    if not settings.allowed_user_ids:
        return True
    return bool(user_id) and user_id in settings.allowed_user_ids
