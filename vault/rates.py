"""Exchange rate engine — rates are automatic, never prompted from staff."""

from __future__ import annotations

import os
from decimal import Decimal, ROUND_HALF_UP

MONEY = Decimal("0.01")
USDT = Decimal("0.0001")
RATE = Decimal("0.01")


def _decimal(value: str | float | Decimal, quant: Decimal) -> Decimal:
    return Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP)


class RateEngine:
    """Calculates THB/USDT conversions and spread."""

    def __init__(
        self,
        buy_rate: Decimal | None = None,
        sell_rate: Decimal | None = None,
    ):
        self.buy_rate = buy_rate or _decimal(
            os.environ.get("BUY_RATE", "39.89"), RATE
        )
        self.sell_rate = sell_rate or _decimal(
            os.environ.get("SELL_RATE", "40.00"), RATE
        )

    @property
    def profit_pct(self) -> Decimal:
        if self.buy_rate <= 0:
            return Decimal("0.00")
        return ((self.sell_rate - self.buy_rate) / self.buy_rate * 100).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    def from_thb(self, thb: Decimal) -> dict[str, Decimal]:
        thb = _decimal(thb, MONEY)
        usdt = (thb / self.buy_rate).quantize(USDT, rounding=ROUND_HALF_UP)
        return {
            "thb": thb,
            "usdt": usdt,
            "buy_rate": self.buy_rate,
            "sell_rate": self.sell_rate,
            "profit_pct": self.profit_pct,
        }

    def from_usdt(self, usdt: Decimal) -> dict[str, Decimal]:
        usdt = _decimal(usdt, USDT)
        thb = (usdt * self.buy_rate).quantize(MONEY, rounding=ROUND_HALF_UP)
        return {
            "thb": thb,
            "usdt": usdt,
            "buy_rate": self.buy_rate,
            "sell_rate": self.sell_rate,
            "profit_pct": self.profit_pct,
        }
