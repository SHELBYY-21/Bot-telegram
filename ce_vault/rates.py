"""Automatic rate engine — staff never enter Buy Rate."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RateQuote:
    buy_rate: float
    sell_rate: float
    profit_pct: float
    thb: float
    usdt: float


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def current_rates() -> tuple[float, float]:
    """Return (buy_rate, sell_rate) from environment with safe defaults."""
    buy = _env_float("BUY_RATE", 39.89)
    sell = _env_float("SELL_RATE", 40.00)
    if buy <= 0:
        buy = 39.89
    if sell <= 0:
        sell = 40.00
    return buy, sell


def profit_pct(buy_rate: float, sell_rate: float) -> float:
    if buy_rate <= 0:
        return 0.0
    return ((sell_rate - buy_rate) / buy_rate) * 100.0


def quote_from_thb(thb: float, buy_rate: float | None = None, sell_rate: float | None = None) -> RateQuote:
    buy, sell = current_rates()
    if buy_rate is not None:
        buy = buy_rate
    if sell_rate is not None:
        sell = sell_rate
    usdt = round(thb / buy, 4) if buy else 0.0
    return RateQuote(
        buy_rate=buy,
        sell_rate=sell,
        profit_pct=round(profit_pct(buy, sell), 2),
        thb=round(thb, 2),
        usdt=usdt,
    )


def quote_from_usdt(usdt: float, buy_rate: float | None = None, sell_rate: float | None = None) -> RateQuote:
    buy, sell = current_rates()
    if buy_rate is not None:
        buy = buy_rate
    if sell_rate is not None:
        sell = sell_rate
    thb = round(usdt * buy, 2) if buy else 0.0
    return RateQuote(
        buy_rate=buy,
        sell_rate=sell,
        profit_pct=round(profit_pct(buy, sell), 2),
        thb=thb,
        usdt=round(usdt, 4),
    )
