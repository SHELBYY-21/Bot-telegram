import pytest

from carta import convert_safe


def test_cap_wins_when_cap_price_is_lower():
    # cap price = 5,000,000 / 20,000,000 = 0.25
    # discount price = 2.50 * 0.8 = 2.00
    result = convert_safe(
        investment=100_000,
        valuation_cap=5_000_000,
        discount_percent=20,
        round_price_per_share=2.50,
        pre_round_fully_diluted_shares=20_000_000,
    )
    assert result.basis == "cap"
    assert result.conversion_price == pytest.approx(0.25)
    assert result.shares_issued == pytest.approx(400_000)
    assert result.ownership_pct == pytest.approx(
        400_000 / (20_000_000 + 400_000) * 100
    )


def test_discount_wins_when_discount_price_is_lower():
    # cap price = 50,000,000 / 20,000,000 = 2.50
    # discount price = 2.00 * 0.8 = 1.60
    result = convert_safe(
        investment=100_000,
        valuation_cap=50_000_000,
        discount_percent=20,
        round_price_per_share=2.00,
        pre_round_fully_diluted_shares=20_000_000,
    )
    assert result.basis == "discount"
    assert result.conversion_price == pytest.approx(1.60)
    assert result.shares_issued == pytest.approx(62_500)


def test_cap_only_when_discount_is_zero():
    result = convert_safe(
        investment=100_000,
        valuation_cap=5_000_000,
        discount_percent=0,
        round_price_per_share=2.50,
        pre_round_fully_diluted_shares=20_000_000,
    )
    assert result.basis == "cap"
    assert result.conversion_price == pytest.approx(0.25)


def test_discount_only_when_cap_is_zero():
    result = convert_safe(
        investment=100_000,
        valuation_cap=0,
        discount_percent=20,
        round_price_per_share=2.00,
        pre_round_fully_diluted_shares=20_000_000,
    )
    assert result.basis == "discount"
    assert result.conversion_price == pytest.approx(1.60)


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(investment=0, valuation_cap=1, discount_percent=0, round_price_per_share=1, pre_round_fully_diluted_shares=1),
        dict(investment=1, valuation_cap=-1, discount_percent=0, round_price_per_share=1, pre_round_fully_diluted_shares=1),
        dict(investment=1, valuation_cap=1, discount_percent=100, round_price_per_share=1, pre_round_fully_diluted_shares=1),
        dict(investment=1, valuation_cap=1, discount_percent=-1, round_price_per_share=1, pre_round_fully_diluted_shares=1),
        dict(investment=1, valuation_cap=1, discount_percent=0, round_price_per_share=0, pre_round_fully_diluted_shares=1),
        dict(investment=1, valuation_cap=1, discount_percent=0, round_price_per_share=1, pre_round_fully_diluted_shares=0),
        dict(investment=1, valuation_cap=0, discount_percent=0, round_price_per_share=1, pre_round_fully_diluted_shares=1),
    ],
)
def test_invalid_inputs_raise(kwargs):
    with pytest.raises(ValueError):
        convert_safe(**kwargs)
