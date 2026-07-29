"""Tests for rate desk math."""

import pytest

from vault.rates import RateQuote, compute_from_thb, compute_from_usdt


def test_profit_and_usdt_from_thb():
    q = RateQuote(buy_rate=39.89, sell_rate=40.00)
    assert round(q.profit_pct, 2) == 0.28  # (40-39.89)/39.89*100
    out = compute_from_thb(500, q)
    assert out["thb"] == 500.0
    assert out["usdt"] == 12.5
    assert out["buy_rate"] == 39.89
    assert out["sell_rate"] == 40.0


def test_thb_from_usdt():
    q = RateQuote(buy_rate=39.89, sell_rate=40.00)
    out = compute_from_usdt(12.5342, q)
    assert out["usdt"] == 12.5342
    assert out["thb"] == 501.37


def test_invalid_sell_rate():
    q = RateQuote(buy_rate=40, sell_rate=0)
    with pytest.raises(ValueError):
        q.usdt_from_thb(100)
