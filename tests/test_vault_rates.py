from decimal import Decimal

from vault.rates import RateEngine


def test_from_thb_calculates_usdt():
    engine = RateEngine(Decimal("39.89"), Decimal("40.00"))
    result = engine.from_thb(Decimal("500"))
    assert result["thb"] == Decimal("500.00")
    assert result["usdt"] == Decimal("12.5345")
    assert result["profit_pct"] == Decimal("0.28")


def test_from_usdt_calculates_thb():
    engine = RateEngine(Decimal("39.89"), Decimal("40.00"))
    result = engine.from_usdt(Decimal("12.5342"))
    assert result["usdt"] == Decimal("12.5342")
    assert result["thb"] == Decimal("499.99")


def test_profit_pct_matches_spec_example():
    engine = RateEngine(Decimal("39.89"), Decimal("40.00"))
    # (40 - 39.89) / 39.89 * 100 = 0.2757... rounds to 0.28
    assert engine.profit_pct == Decimal("0.28")
