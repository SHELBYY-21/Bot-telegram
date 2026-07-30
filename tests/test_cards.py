"""Card rendering — one card, monospace money, status glow."""

from ce_vault import cards
from ce_vault.status import render_status_rail


def test_header_brand():
    out = cards.header("LV-20260318-0001")
    assert "CE VAULT" in out
    assert "Secure Ledger" in out
    assert "LV-20260318-0001" in out
    assert "<code>" in out


def test_status_rail_only_one_active_glows():
    out = render_status_rail("OCR VERIFIED")
    assert "<b>● OCR VERIFIED</b>" in out
    assert "○ RECEIVED" in out
    assert "○ WAITING USDT" in out
    assert out.count("<b>") == 1


def test_confirmation_card_monospace_numbers():
    out = cards.confirmation_card(
        ledger_id="LV-1",
        thb=500,
        usdt=12.5342,
        buy_rate=39.89,
        sell_rate=40.00,
        profit_pct=0.28,
        bank="SCB",
        last4="3376",
        confidence=98.6,
    )
    assert "<code>500.00</code>" in out
    assert "<code>12.5342</code>" in out
    assert "SCB" in out
    assert "3376" in out


def test_ocr_card_layout():
    out = cards.ocr_card(
        ledger_id="LV-2",
        confidence=98.4,
        receiver_name="นายสมชาย",
        bank="SCB",
        last4="3376",
        amount=500,
        verified=True,
        warn=True,
        duplicate=True,
        repeat_receiver=True,
        repeat_count=52,
    )
    assert "Vision" in out
    assert "98.4%" in out
    assert "Duplicate slip" in out
    assert "Known receiver" in out


def test_history_card():
    out = cards.history_card(
        bank="SCB",
        last4="3376",
        tx_count=52,
        total_thb=1_286_500,
        total_usdt=31_944,
        first_seen="2026-03-18T00:00:00+00:00",
        last_seen=None,
    )
    assert "52 Transactions" in out
    assert "1,286,500.00" in out


def test_error_card_only_three_fields():
    out = cards.error_card(
        problem="Duplicate slip",
        cause="Hash already settled",
        action="Use /status on the original ledger",
    )
    assert "Problem" in out
    assert "Cause" in out
    assert "Action" in out
    assert "Buy Rate" not in out


def test_success_card_minimal():
    out = cards.success_card(
        ledger_id="LV-9",
        profit_pct=1.38,
        profit_thb=6.90,
        balance_usdt=25,
    )
    assert "SETTLED" in out
    assert "Done." in out
    assert "+1.38%" in out


def test_console_home_shows_float():
    out = cards.console_home(buy_rate=39.89, sell_rate=40.0, balance_usdt=1000.5)
    assert "39.89" in out
    assert "1,000.5000" in out or "1000.5000" in out
