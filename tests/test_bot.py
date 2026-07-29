"""Bot auth + helper smoke tests for CE VAULT console."""

import bot
from ce_vault.config import allowed_user_ids


def test_allowed_user_ids_parsing(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_IDS", "1, 2  3,4")
    assert allowed_user_ids() == {1, 2, 3, 4}
    monkeypatch.setenv("ALLOWED_USER_IDS", "")
    assert allowed_user_ids() == set()


def test_authorized_open_when_no_allowlist(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_IDS", "")

    class U:
        class effective_user:
            id = 999

    assert bot.authorized(U()) is True


def test_usdt_regex():
    assert bot.USDT_RE.match("12.5")
    assert bot.USDT_RE.match("12.5 USDT")
    assert bot.USDT_RE.match("usdt 3")
    assert not bot.USDT_RE.match("hello")
