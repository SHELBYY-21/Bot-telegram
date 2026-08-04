"""Card rendering — CE VAULT design language.

One card, boxed title, UPPERCASE headings, monospace numbers, one badge.
"""

from ce_vault import cards


def test_header_brand_boxed():
    out = cards.header("CE-20260318-D976")
    assert "CE VAULT" in out
    # Header uses the boxed frame primitive
    assert "╭" in out and "╯" in out
    assert "CE-20260318-D976" in out


def test_ocr_card_shape():
    out = cards.ocr_card(
        ledger_id="CE-20260712-D976",
        confidence=98.4,
        receiver_name="นายสันติภาพ ชูแก้ว",
        bank="SCB",
        last4="3376",
        amount=500,
        slip_datetime="2026-07-12T11:06:00",
        verified=True,
    )
    assert "CE VAULT" in out
    assert "VERIFIED" in out and "98.4%" in out
    assert "AMOUNT" in out and "500.00 THB" in out
    assert "RECEIVER" in out and "SCB" in out and "3376" in out
    assert "นายสันติภาพ" in out
    assert "DATE" in out and "12 Jul 2026" in out and "11:06" in out
    assert "NEXT" in out and "USDT" in out
    assert "#CE-20260712-D976" in out


def test_ocr_card_review_when_duplicate():
    out = cards.ocr_card(
        ledger_id="CE-1",
        confidence=98.4,
        receiver_name="X",
        bank="SCB",
        last4="3376",
        amount=500,
        duplicate=True,
    )
    assert "REVIEW" in out
    assert "Duplicate slip" in out


def test_receive_card_waiting():
    """Card 2 — Transaction Preview / Waiting for USDT."""
    out = cards.receive_card(
        ledger_id="CE-1",
        thb=500.0,
        usdt=None,
        buy_rate=None,
        sell_rate=40.0,
        bank="SCB",
        last4="3376",
        hint="Waiting for settlement…",
    )
    assert "Transaction Preview" in out
    assert "Waiting..." in out
    # Buy rate placeholder when USDT not yet entered
    assert "—" in out
    assert "Waiting for settlement" in out


def test_confirmation_card_shows_estimated_profit_thb():
    out = cards.confirmation_card(
        ledger_id="CE-1",
        thb=500,
        usdt=12.5,
        buy_rate=40.00,
        sell_rate=40.10,
        profit_pct=0.25,
        bank="SCB",
        last4="3376",
        history_count=52,
    )
    assert "Confirm Transaction" in out
    assert "500.00" in out
    assert "12.5000" in out
    # 12.5 * (40.10 - 40.00) = 1.25 THB
    assert "+1.25" in out
    assert "History" in out and "52 Transactions" in out


def test_success_card_carries_receipt():
    out = cards.success_card(
        ledger_id="CE-20260712-D976",
        profit_pct=None,
        profit_thb=1.25,
        thb=500.0,
        usdt=12.5,
        buy_rate=40.0,
        sell_rate=40.1,
        balance_usdt=15091.38,
    )
    assert "Transaction Settled" in out
    assert "SETTLED" in out
    assert "#CE-20260712-D976" in out
    assert "+1.25" in out
    assert "15,091.38 USDT" in out


def test_error_card_minimal():
    out = cards.error_card(problem="Bad amount", action="Send a positive USDT amount.")
    assert "Action Required" in out
    assert "Bad amount" in out
    assert "positive USDT" in out


def test_duplicate_slip_card_shape():
    out = cards.duplicate_slip_card(
        previous_time="2026-07-12T11:21:00+07:00",
        previous_ledger_id="CE-20260712-D842",
    )
    assert "Duplicate Slip Detected" in out
    assert "Previous" in out
    assert "#CE-20260712-D842" in out


def test_today_card_full():
    out = cards.today_card(
        summary={
            "tx_count": 128,
            "thb": 2_481_000.0,
            "profit_thb": 39_812.0,
            "pending": 3,
            "settled": 125,
            "ocr_accuracy": 99.42,
        },
        balance_usdt=15_098.34,
    )
    assert "Today" in out
    assert "Transactions" in out and "128" in out
    assert "Volume" in out and "2,481,000" in out
    assert "Profit" in out and "39,812" in out
    assert "Pending" in out and "Completed" in out and "125" in out
    assert "Wallet" in out and "15,098.34 USDT" in out
    assert "OCR Accuracy" in out and "99.42%" in out


def test_edit_card_shows_shorthand():
    out = cards.edit_card(ledger_id="CE-1", thb=500, usdt=12.5, bank="SCB", last4="3376")
    assert "Edit Transaction" in out
    assert "500.00" in out and "12.5000" in out
    assert "THB 500" in out
    assert "+500" in out and "-12.5U" in out


def test_console_home_shows_float():
    out = cards.console_home(buy_rate=39.89, sell_rate=40.0, balance_usdt=1000.5)
    assert "CE VAULT" in out
    assert "39.89" in out
    assert "1,000.5000" in out
