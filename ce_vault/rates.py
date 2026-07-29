"""Automatic rate engine — staff never enter buy rate."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RateQuote:
    buy_rate: float
    sell_rate: float
    thb: float
    usdt: float
    profit_pct: float
    profit_thb: float


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return float(raw)


def current_rates() -> tuple[float, float]:
    """Return (buy_rate, sell_rate) from environment / defaults.

    Buy rate  — vault acquisition cost (THB per USDT)
    Sell rate — customer conversion rate (THB per USDT)
    """
    buy = _env_float("BUY_RATE", 39.89)
    sell = _env_float("SELL_RATE", 40.00)
    if buy <= 0 or sell <= 0:
        raise ValueError("Rates must be positive")
    return buy, sell


def quote_from_thb(thb: float, buy_rate: float | None = None, sell_rate: float | None = None) -> RateQuote:
    """Customer deposits THB → vault pays USDT at sell rate."""
    buy, sell = current_rates()
    if buy_rate is not None:
        buy = buy_rate
    if sell_rate is not None:
        sell = sell_rate
    if thb <= 0:
        raise ValueError("THB must be positive")
    usdt = thb / sell
    cost = usdt * buy
    profit_thb = thb - cost
    profit_pct = ((sell - buy) / buy) * 100.0
    return RateQuote(
        buy_rate=round(buy, 4),
        sell_rate=round(sell, 4),
        thb=round(thb, 2),
        usdt=round(usdt, 4),
        profit_pct=round(profit_pct, 2),
        profit_thb=round(profit_thb, 2),
    )


def quote_from_usdt(usdt: float, buy_rate: float | None = None, sell_rate: float | None = None) -> RateQuote:
    """Staff enters USDT amount → THB implied at sell rate."""
    buy, sell = current_rates()
    if buy_rate is not None:
        buy = buy_rate
    if sell_rate is not None:
        sell = sell_rate
    if usdt <= 0:
        raise ValueError("USDT must be positive")
    thb = usdt * sell
    cost = usdt * buy
    profit_thb = thb - cost
    profit_pct = ((sell - buy) / buy) * 100.0
    return RateQuote(
        buy_rate=round(buy, 4),
        sell_rate=round(sell, 4),
        thb=round(thb, 2),
        usdt=round(usdt, 4),
        profit_pct=round(profit_pct, 2),
        profit_thb=round(profit_thb, 2),
    )
