"""Tests for CE VAULT UI cards, rates, OCR heuristics, and ledger store."""

from __future__ import annotations

import json

import pytest

from ce_vault.config import Settings
from ce_vault.db import LedgerStore
from ce_vault.models import OCRResult, Transaction, iso
from ce_vault.services.ledger import LedgerService, new_ledger_id, slip_hash_bytes
from ce_vault.services.ocr import OCRService
from ce_vault.services.rates import profit_pct, quote_from_thb, quote_from_usdt
from ce_vault.ui import cards
from ce_vault.ui.status import status_rail
from ce_vault.ui.theme import fmt_pct, fmt_thb, fmt_usdt, mono


def test_status_rail_glows_only_active():
    rail = status_rail("OCR VERIFIED")
    assert "● <b>OCR VERIFIED</b>" in rail
    assert "○ RECEIVED" in rail
    assert "○ WAITING USDT" in rail
    assert rail.count("●") == 1


def test_confirmation_card_is_single_card_with_mono_numbers():
    tx = Transaction(
        ledger_id="LD-260729-ABC123",
        status="OCR VERIFIED",
        thb=500.0,
        usdt=12.5342,
        buy_rate=39.89,
        sell_rate=40.0,
        profit_pct=0.28,
        bank="SCB",
        last4="3376",
        confidence=98.6,
        created_at=iso(),
        updated_at=iso(),
    )
    out = cards.confirmation_card(tx)
    assert "CE VAULT" in out
    assert "LD-260729-ABC123" in out
    assert "<code>500.00</code>" in out
    assert "<code>12.5342</code>" in out
    assert "SCB ••••3376" in out
    assert out.count("CE VAULT") == 1


def test_ocr_card_warns_below_90():
    tx = Transaction(
        ledger_id="LD-1",
        status="RECEIVED",
        created_at=iso(),
        updated_at=iso(),
    )
    ocr = OCRResult(
        receiver_name="นายทดสอบ",
        bank="SCB",
        last4="3376",
        amount_thb=500,
        confidence=82.0,
        verified=False,
    )
    out = cards.ocr_card(tx, ocr)
    assert "Vision" in out
    assert "82.0%" in out
    assert "CONFIDENCE BELOW 90%" in out


def test_error_card_only_three_fields():
    out = cards.error_card(
        problem="Duplicate slip",
        cause="Matches LD-1",
        action="Void prior entry",
        ledger_id="LD-1",
    )
    assert "Problem" in out
    assert "Cause" in out
    assert "Action" in out
    assert "Buy Rate" not in out


def test_history_card_layout():
    from ce_vault.models import ReceiverHistory

    hist = ReceiverHistory(
        bank="SCB",
        last4="3376",
        receiver_name="นายทดสอบ",
        tx_count=52,
        total_thb=1_286_500,
        total_usdt=31_944,
        first_seen="2026-03-18T00:00:00Z",
        last_seen=iso(),
        risk="LOW",
    )
    out = cards.history_card(hist)
    assert "52 Transactions" in out
    assert "1,286,500.00" in out
    assert "LOW" in out


def test_quote_from_thb_matches_buy_rate():
    q = quote_from_thb(500, 39.89, 40.0)
    assert q.usdt == round(500 / 39.89, 4)
    assert q.profit_pct == round(profit_pct(39.89, 40.0), 2)


def test_quote_from_usdt():
    q = quote_from_usdt(12.5342, 39.89, 40.0)
    assert q.thb == round(12.5342 * 39.89, 2)


def test_fmt_helpers():
    assert fmt_thb(500) == "500.00"
    assert fmt_usdt(12.5342) == "12.5342"
    assert fmt_pct(1.38) == "+1.38%"
    assert "<code>12.5</code>" == mono(12.5)


@pytest.mark.asyncio
async def test_heuristic_ocr_parses_thai_slip():
    settings = Settings(
        telegram_token="x",
        allowed_user_ids=frozenset(),
        db_path=__import__("pathlib").Path(":memory:"),
        images_dir=__import__("pathlib").Path("/tmp"),
        buy_rate=39.89,
        sell_rate=40.0,
        ocr_provider="heuristic",
        openai_api_key=None,
        default_staff="ops",
    )
    # Use real temp db path instead of :memory: for Settings path — OCR doesn't need db
    ocr = OCRService(settings)
    text = "โอนสำเร็จ SCB xxxx3376 นายสมชาย ใจดี THB 500.00"
    result = await ocr.extract(caption=text)
    assert result.bank == "SCB"
    assert result.last4 == "3376"
    assert result.amount_thb == 500.0
    assert result.confidence >= 90


def test_ledger_duplicate_and_settle(tmp_path):
    settings = Settings(
        telegram_token="x",
        allowed_user_ids=frozenset(),
        db_path=tmp_path / "ledger.db",
        images_dir=tmp_path / "images",
        buy_rate=39.89,
        sell_rate=40.0,
        ocr_provider="heuristic",
        openai_api_key=None,
        default_staff="ops",
    )
    store = LedgerStore(settings.db_path)
    ledger = LedgerService(store, settings)

    digest = slip_hash_bytes(b"slip-bytes")
    tx = ledger.create_from_slip(
        staff="alice", staff_id=1, chat_id=9, slip_hash=digest
    )
    assert tx.status == "RECEIVED"
    assert ledger.check_duplicate_slip(digest).ledger_id == tx.ledger_id

    ocr = OCRResult(
        receiver_name="นายทดสอบ",
        bank="SCB",
        last4="3376",
        amount_thb=500,
        confidence=98.4,
        verified=True,
    )
    tx = ledger.apply_ocr(tx, ocr)
    assert tx.usdt == round(500 / 39.89, 4)
    assert tx.status == "OCR VERIFIED"

    tx = ledger.confirm(tx)
    assert tx.status == "WAITING USDT"
    tx, bal = ledger.settle(tx)
    assert tx.status == "SETTLED"
    assert bal == tx.usdt

    hist = store.receiver_history("SCB", "3376")
    assert hist is not None
    assert hist.tx_count == 1
    store.close()


def test_new_ledger_id_format():
    lid = new_ledger_id()
    assert lid.startswith("LD-")
    assert len(lid) >= 12


def test_allowed_settings_parsing(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("ALLOWED_USER_IDS", "1, 2  3")
    monkeypatch.setenv("BUY_RATE", "39.5")
    monkeypatch.setenv("SELL_RATE", "40.1")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    s = Settings.from_env()
    assert s.allowed_user_ids == frozenset({1, 2, 3})
    assert s.buy_rate == 39.5
    assert s.sell_rate == 40.1
