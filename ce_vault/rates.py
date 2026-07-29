"""Rate engine — buy/sell/profit calculated automatically."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


TWOPLACES = Decimal("0.01")
CRYPTO = Decimal("0.0001")


@dataclass(frozen=True)
class Quote:
    thb: Decimal
    usdt: Decimal
    buy_rate: Decimal
    sell_rate: Decimal
    profit_pct: Decimal
    profit_thb: Decimal

    def as_dict(self) -> dict:
        return {
            "thb": float(self.thb),
            "usdt": float(self.usdt),
            "buy_rate": float(self.buy_rate),
            "sell_rate": float(self.sell_rate),
            "profit_pct": float(self.profit_pct),
            "profit_thb": float(self.profit_thb),
        }


def _q(value: float | str | Decimal, places: Decimal) -> Decimal:
    return Decimal(str(value)).quantize(places, rounding=ROUND_HALF_UP)


class RateEngine:
    """Sell rate prices customer USDT; buy rate is vault cost basis."""

    def __init__(self, buy_rate: float, sell_rate: float):
        self.buy_rate = _q(buy_rate, TWOPLACES)
        self.sell_rate = _q(sell_rate, TWOPLACES)
        if self.sell_rate <= 0 or self.buy_rate <= 0:
            raise ValueError("rates must be positive")

    def update(self, *, buy_rate: float | None = None, sell_rate: float | None = None) -> None:
        if buy_rate is not None:
            self.buy_rate = _q(buy_rate, TWOPLACES)
        if sell_rate is not None:
            self.sell_rate = _q(sell_rate, TWOPLACES)

    def from_thb(self, thb: float | str | Decimal) -> Quote:
        amount = _q(thb, TWOPLACES)
        usdt = (amount / self.sell_rate).quantize(CRYPTO, rounding=ROUND_HALF_UP)
        return self._quote(amount, usdt)

    def from_usdt(self, usdt: float | str | Decimal) -> Quote:
        amount_usdt = _q(usdt, CRYPTO)
        thb = (amount_usdt * self.sell_rate).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        return self._quote(thb, amount_usdt)

    def _quote(self, thb: Decimal, usdt: Decimal) -> Quote:
        # Profit vs vault acquisition cost at buy rate.
        cost = (usdt * self.buy_rate).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        profit_thb = (thb - cost).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        if self.buy_rate == 0:
            profit_pct = Decimal("0")
        else:
            profit_pct = (
                (self.sell_rate - self.buy_rate) / self.buy_rate * Decimal("100")
            ).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        return Quote(
            thb=thb,
            usdt=usdt,
            buy_rate=self.buy_rate,
            sell_rate=self.sell_rate,
            profit_pct=profit_pct,
            profit_thb=profit_thb,
        )
