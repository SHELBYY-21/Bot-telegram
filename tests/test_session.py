"""Session store + legacy auth helper surface."""

import json

from ce_vault.config import Settings
from ce_vault.session import SessionStore


def test_session_round_trip(tmp_path):
    path = tmp_path / "state.json"
    store = SessionStore(path)
    store.update(42, active_ledger_id="LED-1", mode="edit", console_message_id=99)
    store2 = SessionStore(path)
    sess = store2.get(42)
    assert sess.active_ledger_id == "LED-1"
    assert sess.mode == "edit"
    assert sess.console_message_id == 99
    raw = json.loads(path.read_text())
    assert "sessions" in raw


def test_session_corrupt_file(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not json")
    store = SessionStore(path)
    assert store.get(1).mode == "idle"


def test_settings_rates(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("BUY_RATE", "39.50")
    monkeypatch.setenv("SELL_RATE", "40.10")
    monkeypatch.setenv("LEDGER_DB", str(tmp_path / "x.db"))
    monkeypatch.setenv("STATE_FILE", str(tmp_path / "s.json"))
    monkeypatch.setenv("IMAGES_DIR", str(tmp_path / "img"))
    monkeypatch.setenv("ALLOWED_USER_IDS", "1, 2 3")
    s = Settings.from_env()
    assert s.buy_rate == 39.50
    assert s.sell_rate == 40.10
    assert s.allowed_user_ids == frozenset({1, 2, 3})
