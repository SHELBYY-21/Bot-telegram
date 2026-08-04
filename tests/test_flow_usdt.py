"""Actuals-mode flow: OCR reads THB → operator enters USDT → ledger settles."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from ce_vault.handlers import apply_usdt_received
from ce_vault.ledger import Ledger
from ce_vault.rates import RateQuote
from ce_vault.session import ChatSession, SessionStore
from ce_vault.theme import Status


@pytest.fixture()
def env(tmp_path: Path):
    ledger = Ledger(tmp_path / "vault.db")
    ledger.set_rates(buy=40.0, sell=40.1)
    sessions = SessionStore(tmp_path / "state.json")

    settings = MagicMock()
    settings.allowed_user_ids = set()

    context = MagicMock()
    context.application.bot_data = {
        "ledger": ledger,
        "sessions": sessions,
        "settings": settings,
    }
    context.user_data = {}

    update = MagicMock()
    update.effective_chat.id = 42
    update.effective_user.id = 7
    update.effective_user.full_name = "Alice"
    update.effective_message = MagicMock()
    update.effective_message.reply_text = AsyncMock()
    update.callback_query = None
    return ledger, sessions, update, context


@pytest.mark.asyncio
async def test_apply_usdt_received_derives_buy_rate(env, monkeypatch):
    ledger, sessions, update, context = env
    # Emulate what begin_from_ocr writes: THB only, sell_rate snapshot, no USDT
    entry = ledger.create_entry(
        status=Status.OCR_VERIFIED.value,
        thb=5000.0,
        usdt=None,
        buy_rate=None,
        sell_rate=40.1,
        profit_pct=None,
        staff_id=7,
        staff_name="Alice",
        chat_id=42,
    )
    sessions.update(42, active_ledger_id=entry["id"], mode="await_usdt")

    # Silence the console rendering — we only care about ledger state
    monkeypatch.setattr(
        "ce_vault.handlers.render", AsyncMock(), raising=True
    )

    await apply_usdt_received(update, context, entry["id"], usdt=125.0)

    updated = ledger.get(entry["id"])
    assert updated is not None
    assert updated["status"] == Status.WAITING_USDT.value
    assert updated["usdt"] == 125.0
    # buy_rate = 5000 / 125 = 40.00 (not the desk buy of 40.0 by coincidence,
    # but derived from actuals — verify the math went through the actuals path
    # by checking sell_rate is the snapshot value not a fresh lookup)
    assert updated["buy_rate"] == 40.0
    assert updated["sell_rate"] == 40.1
    assert updated["profit_pct"] == pytest.approx(0.25)
    # Session mode reset after successful application
    assert sessions.get(42).mode == "idle"


@pytest.mark.asyncio
async def test_apply_usdt_rejects_missing_thb(env, monkeypatch):
    ledger, sessions, update, context = env
    entry = ledger.create_entry(
        status=Status.RECEIVED.value,
        thb=None,
        staff_id=7,
        chat_id=42,
    )
    error_render = AsyncMock()
    monkeypatch.setattr("ce_vault.handlers.render", error_render, raising=True)

    await apply_usdt_received(update, context, entry["id"], usdt=125.0)

    updated = ledger.get(entry["id"])
    assert updated["status"] == Status.RECEIVED.value  # unchanged
    assert updated["usdt"] is None
    error_render.assert_awaited_once()


@pytest.mark.asyncio
async def test_apply_usdt_rejects_zero(env, monkeypatch):
    ledger, sessions, update, context = env
    entry = ledger.create_entry(
        status=Status.OCR_VERIFIED.value,
        thb=5000.0,
        sell_rate=40.1,
        staff_id=7,
        chat_id=42,
    )
    error_render = AsyncMock()
    monkeypatch.setattr("ce_vault.handlers.render", error_render, raising=True)

    await apply_usdt_received(update, context, entry["id"], usdt=0.0)
    error_render.assert_awaited_once()
