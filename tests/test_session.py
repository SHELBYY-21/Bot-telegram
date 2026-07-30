"""Session store + settings."""

import json

from ce_vault.config import Settings
from ce_vault.session import SessionStore


def test_session_round_trip(tmp_path):
    path = tmp_path / "state.json"
    store = SessionStore(path)
    store.update(42, active_ledger_id="LV-1", mode="edit", console_message_id=99)
    store2 = SessionStore(path)
    sess = store2.get(42)
    assert sess.active_ledger_id == "LV-1"
    assert sess.mode == "edit"
    assert sess.console_message_id == 99
    raw = json.loads(path.read_text())
    assert "sessions" in raw


def test_session_corrupt_file(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not json")
    store = SessionStore(path)
    assert store.get(1).mode == "idle"


def test_settings_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("STATE_FILE", str(tmp_path / "s.json"))
    monkeypatch.setenv("IMAGES_DIR", str(tmp_path / "img"))
    monkeypatch.setenv("ALLOWED_USER_IDS", "1, 2 3")
    monkeypatch.setenv("OCR_WARN_BELOW", "85")
    s = Settings.from_env()
    assert s.allowed_user_ids == frozenset({1, 2, 3})
    assert s.ocr_warn_below == 85.0
