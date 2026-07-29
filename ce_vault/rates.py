"""Automatic rate engine.

Staff never enters Buy Rate. Sell rate is configured once; buy rate is
derived from spread. USDT is computed from THB (or THB from USDT).
"""

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


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def configured_sell_rate() -> float:
    return _env_float("SELL_RATE", 40.00)


def configured_spread() -> float:
    """Absolute THB spread: sell - buy. Default 0.11 → buy 39.89 when sell 40.00."""
    return _env_float("RATE_SPREAD", 0.11)


def buy_rate_from_sell(sell: float | None = None) -> float:
    sell = configured_sell_rate() if sell is None else sell
    return round(sell - configured_spread(), 4)


def profit_pct(buy: float, sell: float) -> float:
    if buy <= 0:
        return 0.0
    return round((sell - buy) / buy * 100.0, 2)


def quote_from_thb(thb: float, sell: float | None = None) -> RateQuote:
    sell_rate = configured_sell_rate() if sell is None else sell
    buy = buy_rate_from_sell(sell_rate)
    usdt = round(thb / buy, 4) if buy else 0.0
    return RateQuote(
        buy_rate=buy,
        sell_rate=sell_rate,
        thb=round(thb, 2),
        usdt=usdt,
        profit_pct=profit_pct(buy, sell_rate),
    )


def quote_from_usdt(usdt: float, sell: float | None = None) -> RateQuote:
    sell_rate = configured_sell_rate() if sell is None else sell
    buy = buy_rate_from_sell(sell_rate)
    thb = round(usdt * buy, 2)
    return RateQuote(
        buy_rate=buy,
        sell_rate=sell_rate,
        thb=thb,
        usdt=round(usdt, 4),
        profit_pct=profit_pct(buy, sell_rate),
    )
