"""Runtime configuration and design tokens for CE VAULT."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ce_vault.theme import Color, OCR_WARN_THRESHOLD  # noqa: F401 — re-export


BRAND = "CE VAULT"
SUBTITLE = "Secure Ledger"

STATUS_PIPELINE = (
    "RECEIVED",
    "OCR VERIFIED",
    "WAITING USDT",
    "SETTLED",
)


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    allowed_user_ids: frozenset[int]
    state_file: Path
    images_dir: Path
    ocr_warn_below: float

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

        warn = os.environ.get("OCR_WARN_BELOW", "").strip()
        return cls(
            telegram_token=token,
            allowed_user_ids=allowed,
            state_file=Path(os.environ.get("STATE_FILE", "state.json")),
            images_dir=Path(os.environ.get("IMAGES_DIR", "data/slips")),
            ocr_warn_below=float(warn) if warn else OCR_WARN_THRESHOLD,
        )
