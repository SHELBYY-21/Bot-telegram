"""Runtime configuration for CE VAULT."""

from __future__ import annotations

import os
from pathlib import Path


def allowed_user_ids() -> set[int]:
    raw = os.environ.get("ALLOWED_USER_IDS", "").strip()
    return {int(x) for x in raw.replace(",", " ").split()} if raw else set()


def ledger_path() -> Path:
    return Path(os.environ.get("LEDGER_DB", "data/ce_vault.db"))


def require_telegram_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN must be set")
    return token
