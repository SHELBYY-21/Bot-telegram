"""Application configuration from environment."""

from __future__ import annotations

import os


def allowed_user_ids() -> set[int]:
    raw = os.environ.get("ALLOWED_USER_IDS", "").strip()
    return {int(x) for x in raw.replace(",", " ").split()} if raw else set()


def confidence_warning_threshold() -> float:
    return float(os.environ.get("OCR_CONFIDENCE_WARN", "90"))
