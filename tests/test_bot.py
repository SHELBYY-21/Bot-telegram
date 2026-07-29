"""Backward-compatible helpers retained from the previous bot shell."""

import json

import bot
import ce_vault.compat as compat


def test_allowed_user_ids_parsing(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_IDS", "1, 2  3,4")
    assert bot.allowed_user_ids() == {1, 2, 3, 4}
    monkeypatch.setenv("ALLOWED_USER_IDS", "")
    assert bot.allowed_user_ids() == set()


def test_state_round_trip(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(compat, "STATE_FILE", state_file)

    state = bot.load_state()
    assert state == {}
    settings = bot.chat_settings(state, 42)
    settings["repository"] = "https://github.com/o/r"
    bot.save_state(state)

    assert json.loads(state_file.read_text()) == {"42": {"repository": "https://github.com/o/r"}}
    assert bot.load_state() == {"42": {"repository": "https://github.com/o/r"}}


def test_load_state_corrupt_file(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    state_file.write_text("{not json")
    monkeypatch.setattr(compat, "STATE_FILE", state_file)
    assert bot.load_state() == {}
