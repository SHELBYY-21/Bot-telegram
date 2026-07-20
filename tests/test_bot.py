import json

import bot


def test_fmt_agent_escapes_and_includes_fields():
    agent = {
        "id": "bc_1",
        "name": "Fix <script>",
        "status": "RUNNING",
        "source": {"repository": "https://github.com/o/r"},
        "target": {"branchName": "cursor/fix", "prUrl": "https://github.com/o/r/pull/2"},
        "summary": "did things",
    }
    out = bot.fmt_agent(agent)
    assert "&lt;script&gt;" in out
    assert "<script>" not in out
    assert "bc_1" in out
    assert "RUNNING" in out
    assert "https://github.com/o/r/pull/2" in out
    assert "did things" in out


def test_fmt_agent_minimal():
    out = bot.fmt_agent({"id": "bc_2"})
    assert "bc_2" in out
    assert "UNKNOWN" in out


def test_allowed_user_ids_parsing(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_IDS", "1, 2  3,4")
    assert bot.allowed_user_ids() == {1, 2, 3, 4}
    monkeypatch.setenv("ALLOWED_USER_IDS", "")
    assert bot.allowed_user_ids() == set()


def test_state_round_trip(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(bot, "STATE_FILE", state_file)

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
    monkeypatch.setattr(bot, "STATE_FILE", state_file)
    assert bot.load_state() == {}
