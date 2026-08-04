"""Rate desk — buy/sell USDT rates and profit calculation.

Two calculation modes for a ledger entry:

- Quote mode (compute_from_thb / compute_from_usdt): USDT is derived from
  the published desk rate. Used for pricing screens where the operator
  wants to see "if I sold at today's rate, how much USDT is this THB?".

- Actuals mode (compute_from_thb_and_usdt): operator enters the *actual*
  USDT received for a THB inbound; buy_rate is derived as THB/USDT and
  profit is computed against the day's sell rate snapshot. This is what
  ledger settlements use so each entry reflects the true per-deal margin,
  not the desk's advertised margin.
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


def compute_from_thb_and_usdt(
    thb: float, usdt: float, sell_rate: float
) -> dict[str, float]:
    """Actuals mode — operator entered both sides of the trade.

    buy_rate is derived from what actually happened (THB in ÷ USDT out).
    profit is measured against the sell rate snapshot at the time of the
    trade, so it is stable even if the desk changes rates later.
    """
    if usdt <= 0:
        raise ValueError("usdt must be positive")
    if thb <= 0:
        raise ValueError("thb must be positive")
    if sell_rate <= 0:
        raise ValueError("sell_rate must be positive")
    buy = round(float(thb) / float(usdt), 4)
    profit_thb = round(float(usdt) * (float(sell_rate) - buy), 2)
    profit_pct = round(((sell_rate - buy) / buy) * 100.0, 2) if buy > 0 else 0.0
    return {
        "thb": round(float(thb), 2),
        "usdt": round(float(usdt), 4),
        "buy_rate": buy,
        "sell_rate": round(float(sell_rate), 2),
        "profit_pct": profit_pct,
        "profit_thb": profit_thb,
    }
