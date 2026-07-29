"""Tests for CE VAULT card system and status pipeline."""

from ce_vault import cards
from ce_vault.models import ReceiverProfile, Transaction
from ce_vault.theme import TxStatus, status_pipeline


def test_status_pipeline_single_glow():
    out = status_pipeline(TxStatus.OCR_VERIFIED)
    assert "● <b>OCR VERIFIED</b>" in out
    assert out.count("●") == 1
    assert "○ RECEIVED" in out
    assert "○ WAITING USDT" in out
    assert "○ SETTLED" in out


def test_status_pipeline_no_emoji_circles_only():
    out = status_pipeline("SETTLED")
    assert "🟢" not in out
    assert "● <b>SETTLED</b>" in out


def test_receive_card_monospace_numbers():
    tx = Transaction(
        ledger_id="LV-20260729-TEST01",
        status=TxStatus.OCR_VERIFIED.value,
        thb=500.0,
        usdt=12.5342,
        buy_rate=39.89,
        sell_rate=40.0,
        profit_pct=0.28,
        bank="SCB",
        last4="3376",
        confidence=98.6,
    )
    out = cards.receive_card(tx)
    assert "CE VAULT" in out
    assert "Secure Ledger" in out
    assert "LV-20260729-TEST01" in out
    assert "<code>500.00</code>" in out
    assert "<code>12.5342</code>" in out
    assert "SCB ••••3376" in out
    assert "Confirm" in out


def test_ocr_card_warns_below_90():
    tx = Transaction(
        ledger_id="LV-1",
        confidence=82.0,
        ocr={
            "receiver_name": "นายทดสอบ",
            "bank": "SCB",
            "last4": "3376",
            "amount_thb": 500.0,
            "confidence": 82.0,
            "verified": False,
        },
    )
    out = cards.ocr_card(tx)
    assert "WARN" in out
    assert "Vision" in out
    assert "นายทดสอบ" in out


def test_error_card_only_three_fields():
    out = cards.error_card(problem="Duplicate slip", cause="LV-1", action="Edit original")
    assert "Problem" in out
    assert "Cause" in out
    assert "Action" in out
    assert "Profit" not in out


def test_success_card_minimal():
    tx = Transaction(ledger_id="LV-9", profit_pct=1.38, usdt=12.5)
    out = cards.success_card(tx, balance_usdt=100.5)
    assert "SETTLED" in out
    assert "Done." in out
    assert "Updated Balance" in out


def test_history_card():
    profile = ReceiverProfile(
        bank="SCB",
        last4="3376",
        tx_count=52,
        total_thb=1_286_500,
        total_usdt=31_944,
        first_seen="2026-03-18T00:00:00Z",
        last_seen="2026-07-29T08:00:00Z",
        risk="LOW",
    )
    out = cards.history_card(profile)
    assert "52 Transactions" in out
    assert "1,286,500.00 THB" in out
    assert "LOW" in out
