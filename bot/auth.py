"""Authorization helpers."""

from __future__ import annotations

import os

from telegram import Update


def allowed_user_ids() -> set[int]:
    raw = os.environ.get("ALLOWED_USER_IDS", "").strip()
    return {int(x) for x in raw.replace(",", " ").split()} if raw else set()


def authorized(update: Update) -> bool:
    allowed = allowed_user_ids()
    if not allowed:
        return True
    return bool(update.effective_user) and update.effective_user.id in allowed
