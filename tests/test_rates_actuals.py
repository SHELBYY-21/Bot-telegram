"""compute_from_thb_and_usdt — actuals-mode ledger math."""

import pytest

from ce_vault.rates import compute_from_thb_and_usdt


def test_buy_rate_derived_from_actuals():
    # 5000 THB in for 125 USDT out → buy rate 40.00
    result = compute_from_thb_and_usdt(thb=5000.0, usdt=125.0, sell_rate=40.10)
    assert result["buy_rate"] == 40.0
    assert result["usdt"] == 125.0
    assert result["thb"] == 5000.0


def test_profit_derived_from_snapshot_sell_rate():
    # 5000 THB / 125 USDT = 40.00 buy; sell 40.10 → margin 0.10/USDT × 125 = 12.50
    result = compute_from_thb_and_usdt(thb=5000.0, usdt=125.0, sell_rate=40.10)
    assert result["profit_thb"] == 12.50
    # 0.10/40.00 = 0.25%
    assert result["profit_pct"] == 0.25


def test_negative_profit_when_effective_cost_exceeds_snapshot():
    # buy_rate = THB / USDT. If the operator sent *fewer* USDT than the
    # snapshot sell_rate would have required, the effective per-USDT cost
    # exceeds the target sell — this is booked as a loss.
    result = compute_from_thb_and_usdt(thb=5000.0, usdt=120.0, sell_rate=40.10)
    assert result["buy_rate"] > result["sell_rate"]
    assert result["profit_thb"] < 0
    assert result["profit_pct"] < 0


@pytest.mark.parametrize("usdt", [0, -1])
def test_rejects_nonpositive_usdt(usdt):
    with pytest.raises(ValueError):
        compute_from_thb_and_usdt(thb=5000.0, usdt=usdt, sell_rate=40.10)


def test_rejects_nonpositive_thb():
    with pytest.raises(ValueError):
        compute_from_thb_and_usdt(thb=0, usdt=125.0, sell_rate=40.10)


def test_rejects_nonpositive_sell_rate():
    with pytest.raises(ValueError):
        compute_from_thb_and_usdt(thb=5000.0, usdt=125.0, sell_rate=0)
