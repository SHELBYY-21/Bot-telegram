"""Rate and profit calculations."""

from __future__ import annotations

from dataclasses import dataclass

from db.repository import Repository


@dataclass
class RateSnapshot:
    buy_rate: float
    sell_rate: float

    @property
    def spread(self) -> float:
        return self.sell_rate - self.buy_rate

    def profit_pct(self) -> float:
        if self.buy_rate <= 0:
            return 0.0
        return (self.spread / self.buy_rate) * 100


def get_rates(repo: Repository) -> RateSnapshot:
    return RateSnapshot(
        buy_rate=repo.get_rate("buy_rate", 39.89),
        sell_rate=repo.get_rate("sell_rate", 40.00),
    )


def thb_to_usdt(thb: float, buy_rate: float) -> float:
    if buy_rate <= 0:
        return 0.0
    return round(thb / buy_rate, 4)


def usdt_to_thb(usdt: float, buy_rate: float) -> float:
    return round(usdt * buy_rate, 2)


def calc_profit_pct(buy_rate: float, sell_rate: float) -> float:
    if buy_rate <= 0:
        return 0.0
    return round(((sell_rate - buy_rate) / buy_rate) * 100, 2)
