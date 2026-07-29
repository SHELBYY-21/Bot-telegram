import json
from decimal import Decimal

import bot
from config import allowed_user_ids
from vault.cards import CardRenderer
from vault.models import PipelineStatus, TransactionDraft
from vault.rates import RateEngine
from vault.session import SessionStore


def test_allowed_user_ids_parsing(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_IDS", "1, 2  3,4")
    assert allowed_user_ids() == {1, 2, 3, 4}
    monkeypatch.setenv("ALLOWED_USER_IDS", "")
    assert allowed_user_ids() == set()


def test_session_round_trip(tmp_path, monkeypatch):
    session_file = tmp_path / "state.json"
    monkeypatch.setenv("SESSION_FILE", str(session_file))
    store = SessionStore(session_file)

    session = store.get(42)
    session.draft = TransactionDraft(
        ledger_id="LDG-20260729-0001",
        thb=Decimal("500.00"),
        usdt=Decimal("12.5342"),
        buy_rate=Decimal("39.89"),
        sell_rate=Decimal("40.00"),
        bank="SCB",
        last4="3376",
        status=PipelineStatus.WAITING_USDT,
    )
    session.mode = "confirm"
    session.active_message_id = 99
    store.save()

    reloaded = SessionStore(session_file)
    loaded = reloaded.get(42)
    assert loaded.mode == "confirm"
    assert loaded.active_message_id == 99
    assert loaded.draft is not None
    assert loaded.draft.thb == Decimal("500.00")
    assert loaded.draft.status == PipelineStatus.WAITING_USDT


def test_draft_profit_calculation():
    draft = TransactionDraft(
        ledger_id="LDG-1",
        thb=Decimal("500"),
        usdt=Decimal("12.5342"),
        buy_rate=Decimal("39.89"),
        sell_rate=Decimal("40.00"),
    )
    assert draft.profit_pct == Decimal("0.28")
    assert draft.masked_receiver == "—"


def test_rate_engine_env_defaults(monkeypatch):
    monkeypatch.delenv("BUY_RATE", raising=False)
    monkeypatch.delenv("SELL_RATE", raising=False)
    engine = RateEngine()
    assert engine.buy_rate == Decimal("39.89")
    assert engine.sell_rate == Decimal("40.00")


def test_card_renderer_dashboard():
    totals = {"count": 3, "thb": Decimal("1500"), "usdt": Decimal("37.5")}
    text = CardRenderer.dashboard_card(
        totals, (Decimal("39.89"), Decimal("40.00"), Decimal("0.28"))
    )
    assert "CE VAULT" in text
    assert "1,500.00" in text
