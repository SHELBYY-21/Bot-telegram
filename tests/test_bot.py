import bot
from ce_vault.ledger import Ledger
from ce_vault.store import create_ledger
from ce_vault.supabase_ledger import SupabaseLedger


def test_build_app_wires_handlers(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "0000000000:TEST_TOKEN_FOR_UNIT_TESTS_ONLY")
    monkeypatch.setenv("LEDGER_BACKEND", "sqlite")
    monkeypatch.setenv("LEDGER_DB", str(tmp_path / "ledger.db"))
    monkeypatch.setenv("STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setenv("IMAGES_DIR", str(tmp_path / "slips"))
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    app = bot.build_app()
    assert "ledger" in app.bot_data
    assert "sessions" in app.bot_data
    assert isinstance(app.bot_data["ledger"], Ledger)
    assert len(app.handlers[0]) >= 10


def test_create_ledger_defaults_to_sqlite(monkeypatch, tmp_path):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.setenv("LEDGER_BACKEND", "sqlite")
    monkeypatch.setenv("LEDGER_DB", str(tmp_path / "t.db"))

    store = create_ledger()
    assert isinstance(store, Ledger)


def test_create_ledger_prefers_secret_key(monkeypatch):
    monkeypatch.setenv("LEDGER_BACKEND", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    store = create_ledger()
    assert isinstance(store, SupabaseLedger)
    store.close()
