"""Automatic buy/sell rate and profit calculations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RateQuote:
    buy_rate: float
    sell_rate: float
    profit_pct: float
    thb: float
    usdt: float


class RateService:
    def __init__(self, buy_rate: float, sell_rate: float):
        self.buy_rate = buy_rate
        self.sell_rate = sell_rate

    @staticmethod
    def profit_pct(buy_rate: float, sell_rate: float) -> float:
        if buy_rate <= 0:
            return 0.0
        return ((sell_rate - buy_rate) / buy_rate) * 100

    def from_thb(self, thb: float) -> RateQuote:
        usdt = round(thb / self.sell_rate, 4)
        return RateQuote(
            buy_rate=self.buy_rate,
            sell_rate=self.sell_rate,
            profit_pct=round(self.profit_pct(self.buy_rate, self.sell_rate), 2),
            thb=round(thb, 2),
            usdt=usdt,
        )

    def from_usdt(self, usdt: float) -> RateQuote:
        thb = round(usdt * self.sell_rate, 2)
        return RateQuote(
            buy_rate=self.buy_rate,
            sell_rate=self.sell_rate,
            profit_pct=round(self.profit_pct(self.buy_rate, self.sell_rate), 2),
            thb=thb,
            usdt=round(usdt, 4),
        )

    def recalculate(self, thb: float | None, usdt: float | None) -> RateQuote:
        if usdt is not None:
            return self.from_usdt(usdt)
        if thb is not None:
            return self.from_thb(thb)
        raise ValueError("thb or usdt required")
