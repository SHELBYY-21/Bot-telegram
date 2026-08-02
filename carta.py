"""SAFE-to-equity conversion calculator (Carta-style cap table math).

Converts a SAFE (Simple Agreement for Future Equity) investment into shares
and ownership percentage at a priced round, using the standard "lower of
cap price or discount price" conversion mechanic.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConversionResult:
    conversion_price: float
    shares_issued: float
    ownership_pct: float
    basis: str  # "cap" or "discount"


def convert_safe(
    investment: float,
    valuation_cap: float,
    discount_percent: float,
    round_price_per_share: float,
    pre_round_fully_diluted_shares: float,
) -> ConversionResult:
    """Convert a SAFE investment into shares at a priced round.

    The conversion price is the lower of the valuation-cap price
    (cap / pre-round fully diluted shares) and the discounted round price
    (round_price_per_share * (1 - discount)). Pass 0 for valuation_cap or
    discount_percent to disable that term.
    """
    if investment <= 0:
        raise ValueError("investment must be positive")
    if pre_round_fully_diluted_shares <= 0:
        raise ValueError("pre_round_fully_diluted_shares must be positive")
    if round_price_per_share <= 0:
        raise ValueError("round_price_per_share must be positive")
    if valuation_cap < 0:
        raise ValueError("valuation_cap must not be negative")
    if not (0 <= discount_percent < 100):
        raise ValueError("discount_percent must be within [0, 100)")
    if valuation_cap == 0 and discount_percent == 0:
        raise ValueError("specify a valuation_cap, a discount_percent, or both")

    cap_price = (
        valuation_cap / pre_round_fully_diluted_shares if valuation_cap > 0 else None
    )
    discount_price = (
        round_price_per_share * (1 - discount_percent / 100)
        if discount_percent > 0
        else None
    )

    candidates = [p for p in (cap_price, discount_price) if p is not None]
    conversion_price = min(candidates)
    basis = "cap" if conversion_price == cap_price else "discount"

    shares_issued = investment / conversion_price
    ownership_pct = (
        shares_issued / (pre_round_fully_diluted_shares + shares_issued) * 100
    )

    return ConversionResult(
        conversion_price=conversion_price,
        shares_issued=shares_issued,
        ownership_pct=ownership_pct,
        basis=basis,
    )
