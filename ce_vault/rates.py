"""FX rate and profit calculations — never ask the operator for buy rate."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


TWOPLACES = Decimal("0.01")
FOURPLACES = Decimal("0.0001")


@dataclass
class RateBook:
    buy_rate: Decimal
    sell_rate: Decimal

    @classmethod
    def from_floats(cls, buy: float, sell: float) -> "RateBook":
        return cls(buy_rate=Decimal(str(buy)), sell_rate=Decimal(str(sell)))

    def with_rates(self, buy: float | Decimal | None = None, sell: float | Decimal | None = None) -> "RateBook":
        return RateBook(
            buy_rate=Decimal(str(buy)) if buy is not None else self.buy_rate,
            sell_rate=Decimal(str(sell)) if sell is not None else self.sell_rate,
        )

    def thb_to_usdt(self, thb: Decimal | float | str) -> Decimal:
        amount = Decimal(str(thb))
        if self.buy_rate <= 0:
            raise ValueError("buy_rate must be positive")
        return (amount / self.buy_rate).quantize(FOURPLACES, rounding=ROUND_HALF_UP)

    def usdt_to_thb(self, usdt: Decimal | float | str) -> Decimal:
        amount = Decimal(str(usdt))
        return (amount * self.buy_rate).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    def profit_pct(self) -> Decimal:
        if self.buy_rate <= 0:
            raise ValueError("buy_rate must be positive")
        return ((self.sell_rate - self.buy_rate) / self.buy_rate * Decimal(100)).quantize(
            TWOPLACES, rounding=ROUND_HALF_UP
        )

    def profit_thb(self, thb: Decimal | float | str) -> Decimal:
        """Spread captured on a THB notional settled at desk sell rate."""
        amount = Decimal(str(thb))
        usdt = self.thb_to_usdt(amount)
        sell_value = (usdt * self.sell_rate).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        return (sell_value - amount).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
