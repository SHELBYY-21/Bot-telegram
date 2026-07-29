"""Rate engine + OCR parsers + typography."""

from decimal import Decimal

from ce_vault.ocr import extract_from_text, parse_edit_command, parse_usdt_amount
from ce_vault.rates import RateEngine
from ce_vault.typography import bank_receiver, money, pct


def test_quote_from_thb():
    engine = RateEngine(39.89, 40.00)
    q = engine.from_thb(500)
    assert q.thb == Decimal("500.00")
    assert q.usdt == Decimal("12.5000")
    assert q.profit_pct == Decimal("0.28")


def test_quote_from_usdt():
    engine = RateEngine(39.89, 40.00)
    q = engine.from_usdt(12.5)
    assert q.usdt == Decimal("12.5000")
    assert q.thb == Decimal("500.00")


def test_parse_usdt_amount_variants():
    assert parse_usdt_amount("12.5") == 12.5
    assert parse_usdt_amount("USDT 12.5342") == 12.5342
    assert parse_usdt_amount("12.5 USDT") == 12.5
    assert parse_usdt_amount("hello") is None


def test_extract_from_text_slip():
    text = """
    ผู้รับ: นายสมชาย ใจดี
    Bank: SCB
    Account: xxxx3376
    Amount: 500.00 THB
    """
    result = extract_from_text(text)
    assert result.bank == "SCB"
    assert result.last4 == "3376"
    assert result.amount == 500.0
    assert result.confidence >= 90


def test_parse_edit_command():
    assert parse_edit_command("THB 500") == {"thb": 500.0}
    assert parse_edit_command("USDT 12.5") == {"usdt": 12.5}
    assert parse_edit_command("BANK SCB 3376") == {"bank": "SCB", "last4": "3376"}


def test_typography_money_and_receiver():
    assert money(1286500) == "1,286,500.00"
    assert pct(1.38) == "+1.38%"
    assert bank_receiver("SCB", "3376") == "SCB ••••3376"
