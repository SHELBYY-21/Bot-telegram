"""Rate engine + OCR parsers + typography."""

from ce_vault.formatting import mask_account, money, pct
from ce_vault.ocr import DEMO_SLIP_TEXT, parse_edit_command, parse_slip_text, parse_usdt_amount
from ce_vault.rates import RateQuote, compute_from_thb, compute_from_usdt


def test_quote_from_thb():
    q = RateQuote(39.89, 40.00)
    amounts = compute_from_thb(500, q)
    assert amounts["thb"] == 500.0
    assert amounts["usdt"] == 12.5
    assert amounts["profit_pct"] == 0.28


def test_quote_from_usdt():
    q = RateQuote(39.89, 40.00)
    amounts = compute_from_usdt(12.5, q)
    assert amounts["usdt"] == 12.5
    assert amounts["thb"] == 500.0


def test_parse_usdt_amount_variants():
    assert parse_usdt_amount("12.5") == 12.5
    assert parse_usdt_amount("USDT 12.5342") == 12.5342
    assert parse_usdt_amount("12.5 USDT") == 12.5
    assert parse_usdt_amount("hello") is None


def test_parse_demo_slip():
    result = parse_slip_text(DEMO_SLIP_TEXT)
    assert result.bank == "SCB"
    assert result.last4 == "3376"
    assert result.amount_thb == 500.0
    assert result.confidence >= 90


def test_parse_edit_command():
    assert parse_edit_command("THB 500") == {"thb": 500.0}
    assert parse_edit_command("USDT 12.5") == {"usdt": 12.5}
    assert parse_edit_command("BANK SCB 3376") == {"bank": "SCB", "last4": "3376"}


def test_formatting_money_and_receiver():
    assert money(1286500) == "1,286,500.00"
    assert pct(1.38) == "+1.38%"
    assert mask_account("3376", "SCB") == "SCB ••••3376"
