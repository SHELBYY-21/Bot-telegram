"""Legacy bot helper tests — kept for backward compatibility."""

import agents_bridge
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
    out = agents_bridge.fmt_agent(agent)
    assert "&lt;script&gt;" in out
    assert "<script>" not in out
    assert "bc_1" in out
    assert "RUNNING" in out
    assert "https://github.com/o/r/pull/2" in out
    assert "did things" in out


def test_fmt_agent_minimal():
    out = agents_bridge.fmt_agent({"id": "bc_2"})
    assert "bc_2" in out
    assert "UNKNOWN" in out


def test_allowed_user_ids_parsing(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_IDS", "1, 2  3,4")
    assert bot.allowed_user_ids() == {1, 2, 3, 4}
    monkeypatch.setenv("ALLOWED_USER_IDS", "")
    assert bot.allowed_user_ids() == set()
