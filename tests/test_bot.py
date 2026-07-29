"""Bot / config helpers for CE Vault console."""

from __future__ import annotations

import ce_vault.config as config
from ce_vault.config import Settings, is_authorized


def test_is_authorized_open_when_empty():
    s = Settings(
        telegram_token="x",
        allowed_user_ids=frozenset(),
        db_path=__import__("pathlib").Path("t.db"),
        buy_rate=39.89,
        sell_rate=40.0,
        ocr_warn_below=90.0,
        openai_api_key=None,
        ocr_model="gpt-4o-mini",
    )
    assert is_authorized(123, s) is True


def test_is_authorized_allowlist(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_IDS", "1, 2  3")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    s = config.load_settings()
    assert s.allowed_user_ids == frozenset({1, 2, 3})
    assert is_authorized(2, s) is True
    assert is_authorized(99, s) is False


def test_load_settings_requires_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    try:
        config.load_settings()
        assert False, "expected SystemExit"
    except SystemExit:
        pass
