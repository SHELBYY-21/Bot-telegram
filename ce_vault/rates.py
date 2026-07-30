"""Rate desk — buy/sell USDT rates and automatic profit calculation.

Operators never enter a buy rate during a transaction. The desk
publishes rates once; every ledger entry pulls the live desk rates
and derives USDT + profit automatically.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RateQuote:
    buy_rate: float
    sell_rate: float

    @property
    def profit_pct(self) -> float:
        if self.buy_rate <= 0:
            return 0.0
        return ((self.sell_rate - self.buy_rate) / self.buy_rate) * 100.0

    def usdt_from_thb(self, thb: float) -> float:
        if self.sell_rate <= 0:
            raise ValueError("sell_rate must be positive")
        return round(thb / self.sell_rate, 4)

    def thb_from_usdt(self, usdt: float) -> float:
        return round(usdt * self.sell_rate, 2)


def compute_from_thb(thb: float, quote: RateQuote) -> dict[str, float]:
    usdt = quote.usdt_from_thb(thb)
    return {
        "thb": round(float(thb), 2),
        "usdt": usdt,
        "buy_rate": quote.buy_rate,
        "sell_rate": quote.sell_rate,
        "profit_pct": round(quote.profit_pct, 2),
    }


def compute_from_usdt(usdt: float, quote: RateQuote) -> dict[str, float]:
    thb = quote.thb_from_usdt(usdt)
    return {
        "thb": thb,
        "usdt": round(float(usdt), 4),
        "buy_rate": quote.buy_rate,
        "sell_rate": quote.sell_rate,
        "profit_pct": round(quote.profit_pct, 2),
    }
