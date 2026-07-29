"""Tests for CE VAULT design, rates, OCR, ledger, and cards."""

from __future__ import annotations

import json

import bot
from vault import cards, design, rates
from vault.ledger import Ledger
from vault.models import OCRResult, Transaction, TxStatus
from vault.ocr import parse_slip_text


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


def test_status_rail_only_one_active_glows():
    rail = design.status_rail("OCR VERIFIED")
    assert rail.count("<b>●") == 1
    assert "<b>● OCR VERIFIED</b>" in rail
    assert "○ RECEIVED" in rail
    assert "○ WAITING USDT" in rail
    assert "○ SETTLED" in rail


def test_money_and_crypto_monospace_helpers():
    assert design.money(1286500) == "1,286,500.00"
    assert design.crypto(12.5342) == "12.5342"
    assert design.pct(1.38) == "+1.38%"
    assert design.mask_account("3376", "SCB") == "SCB ••••3376"


def test_quote_from_thb_uses_sell_rate(tmp_path, monkeypatch):
    rates_file = tmp_path / "rates.json"
    monkeypatch.setattr(rates, "RATES_FILE", rates_file)
    rates.save_rates(39.89, 40.00)
    q = rates.quote(thb=500)
    assert q["thb"] == 500.0
    assert q["usdt"] == 12.5
    assert q["buy_rate"] == 39.89
    assert q["sell_rate"] == 40.0
    assert q["profit_pct"] == 0.28


def test_quote_from_usdt(tmp_path, monkeypatch):
    rates_file = tmp_path / "rates.json"
    monkeypatch.setattr(rates, "RATES_FILE", rates_file)
    rates.save_rates(39.89, 40.00)
    q = rates.quote(usdt=12.5)
    assert q["thb"] == 500.0
    assert q["usdt"] == 12.5


def test_parse_slip_text_thai_bank():
    text = """
    ผู้รับ นายสมชาย ใจดี
    SCB xxxx3376
    จำนวน 500.00 บาท
    """
    ocr = parse_slip_text(text)
    assert ocr.bank == "SCB"
    assert ocr.last4 == "3376"
    assert ocr.amount_thb == 500.0
    assert ocr.receiver and "สมชาย" in ocr.receiver
    assert ocr.confidence >= 90
    assert ocr.status == "Verified"


def test_parse_slip_low_confidence():
    ocr = parse_slip_text("hello world")
    assert ocr.confidence < 90
    assert ocr.below_threshold


def test_ledger_upsert_history_duplicate(tmp_path):
    db = tmp_path / "ledger.db"
    store = Ledger(db)

    tx = Transaction.create(staff="ops")
    tx.status = TxStatus.SETTLED.value
    tx.thb = 500
    tx.usdt = 12.5
    tx.buy_rate = 39.89
    tx.sell_rate = 40.0
    tx.profit_pct = 0.28
    tx.receiver = "นายสมชาย"
    tx.bank = "SCB"
    tx.last4 = "3376"
    tx.slip_hash = "abc123"
    store.upsert(tx)

    hist = store.receiver_history(last4="3376")
    assert hist is not None
    assert hist.tx_count == 1
    assert hist.total_thb == 500
    assert hist.risk == "LOW"

    assert store.find_by_slip_hash("abc123") is not None
    assert store.has_receiver(last4="3376")

    bal = store.set_balance(usdt=1000, thb=0)
    assert bal["usdt"] == 1000
    store.apply_settlement(tx)
    assert store.get_balance()["usdt"] == 987.5
    assert store.get_balance()["thb"] == 500


def test_transaction_card_is_single_surface():
    tx = Transaction.create()
    tx.status = TxStatus.WAITING_USDT.value
    tx.thb = 500
    tx.usdt = 12.5342
    tx.buy_rate = 39.89
    tx.sell_rate = 40.0
    tx.profit_pct = 1.38
    tx.bank = "SCB"
    tx.last4 = "3376"
    tx.ocr_confidence = 98.6
    out = cards.transaction_card(tx)
    assert "CE VAULT" in out
    assert "Secure Ledger" in out
    assert "<code>500.00</code>" in out
    assert "<code>12.5342</code>" in out
    assert "SCB ••••3376" in out
    assert out.count("<b>●") == 1


def test_ocr_card_warns_below_90():
    tx = Transaction.create()
    tx.status = TxStatus.OCR_VERIFIED.value
    ocr = OCRResult(
        receiver="นาย...",
        bank="SCB",
        last4="3376",
        amount_thb=500,
        confidence=88.0,
        status="Review",
    )
    out = cards.ocr_card(tx, ocr)
    assert "Vision" in out
    assert "Confidence below 90%" in out


def test_error_card_only_three_fields():
    out = cards.error_card(problem="Duplicate slip", cause="hash match", action="Cancel")
    assert "Problem" in out
    assert "Cause" in out
    assert "Action" in out
    assert "Buy Rate" not in out


def test_success_card_minimal():
    tx = Transaction.create()
    tx.profit_pct = 1.38
    out = cards.success_card(tx, balance_usdt=9887.4658)
    assert "SETTLED" in out
    assert "Done." in out
    assert "Updated Balance" in out
