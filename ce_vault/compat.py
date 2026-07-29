"""Legacy auth/state helpers — kept so older scripts importing `bot` still resolve."""

from __future__ import annotations

import json
import os
from pathlib import Path

STATE_FILE = Path(os.environ.get("STATE_FILE", "state.json"))


def allowed_user_ids() -> set[int]:
    raw = os.environ.get("ALLOWED_USER_IDS", "").strip()
    return {int(x) for x in raw.replace(",", " ").split()} if raw else set()


def _state_path() -> Path:
    # Allow tests / callers to monkeypatch STATE_FILE on this module or bot.
    return STATE_FILE


def load_state() -> dict:
    path = _state_path()
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_state(state: dict) -> None:
    _state_path().write_text(json.dumps(state, indent=2))


def chat_settings(state: dict, chat_id: int) -> dict:
    return state.setdefault(str(chat_id), {})
