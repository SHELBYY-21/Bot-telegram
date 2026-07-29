"""Tests for CE VAULT card renderers and formatting."""

from vault import cards
from vault.formatting import crypto, mask_account, money, pct
from vault.theme import Status


def test_money_and_crypto_monospace_ready():
    assert money(500) == "500.00"
    assert money(1286500) == "1,286,500.00"
    assert crypto(12.5342) == "12.5342"
    assert pct(1.38) == "+1.38%"


def test_mask_account():
    assert mask_account("3376", "SCB") == "SCB ••••3376"


def test_receive_card_structure():
    text = cards.receive_card(
        ledger_id="LV-20260729-0001",
        thb=500,
        usdt=12.5342,
        buy_rate=39.89,
        sell_rate=40.0,
        profit=1.38,
        bank="SCB",
        last4="3376",
        conf=98.6,
        status=Status.OCR_VERIFIED,
    )
    assert "CE VAULT" in text
    assert "Secure Ledger" in text
    assert "LV-20260729-0001" in text
    assert "<code>500.00</code>" in text
    assert "<code>12.5342</code>" in text
    assert "<code>+1.38%</code>" in text
    assert "SCB ••••3376" in text
    # Only active status glows (bold)
    assert "<b>● OCR VERIFIED</b>" in text
    assert "<b>● RECEIVED</b>" not in text
    assert "<b>● WAITING USDT</b>" not in text


def test_ocr_card_warns_low_confidence_and_flags():
    text = cards.ocr_card(
        ledger_id="LV-1",
        vision=85.0,
        receiver="นายสมชาย",
        bank="SCB",
        last4="3376",
        amount=500,
        verified=True,
        duplicate=True,
        repeat_receiver=True,
    )
    assert "Vision" in text
    assert "85.0%" in text
    assert "CONFIDENCE BELOW 90%" in text
    assert "DUPLICATE SLIP" in text
    assert "REPEAT RECEIVER" in text


def test_history_card():
    text = cards.history_card(
        bank="SCB",
        last4="3376",
        tx_count=52,
        total_thb=1_286_500,
        total_usdt=31_944,
        first_seen="2026-03-18T00:00:00+00:00",
        last_seen="2026-07-29T00:00:00+00:00",
        risk="LOW",
    )
    assert "52" in text
    assert "1,286,500.00" in text
    assert "31,944.0000" in text
    assert "2026-03-18" in text


def test_success_and_error_cards_are_minimal():
    ok = cards.success_card(ledger_id="LV-9", profit=1.38, balance_usdt=1000)
    assert "Done." in ok
    assert "SETTLED" in ok
    err = cards.error_card(problem="X", cause="Y", action="Z")
    assert "Problem" in err and "Cause" in err and "Action" in err
    assert "THB" not in err
