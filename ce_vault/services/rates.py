"""Rate engine — operators never enter buy rate."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Quote:
    thb: float
    usdt: float
    buy_rate: float
    sell_rate: float
    profit_pct: float


def profit_pct(buy_rate: float, sell_rate: float) -> float:
    if buy_rate <= 0:
        return 0.0
    return ((sell_rate - buy_rate) / buy_rate) * 100.0


def quote_from_thb(thb: float, buy_rate: float, sell_rate: float) -> Quote:
    """Customer THB → USDT at buy rate (desk acquisition)."""
    if buy_rate <= 0:
        raise ValueError("buy_rate must be positive")
    usdt = thb / buy_rate
    return Quote(
        thb=round(thb, 2),
        usdt=round(usdt, 4),
        buy_rate=buy_rate,
        sell_rate=sell_rate,
        profit_pct=round(profit_pct(buy_rate, sell_rate), 2),
    )


def quote_from_usdt(usdt: float, buy_rate: float, sell_rate: float) -> Quote:
    """Operator supplies USDT — THB implied at buy rate."""
    if buy_rate <= 0:
        raise ValueError("buy_rate must be positive")
    thb = usdt * buy_rate
    return Quote(
        thb=round(thb, 2),
        usdt=round(usdt, 4),
        buy_rate=buy_rate,
        sell_rate=sell_rate,
        profit_pct=round(profit_pct(buy_rate, sell_rate), 2),
    )


def apply_quote(tx: object, quote: Quote) -> None:
    """Mutate a Transaction-like object with quote fields."""
    tx.thb = quote.thb  # type: ignore[attr-defined]
    tx.usdt = quote.usdt  # type: ignore[attr-defined]
    tx.buy_rate = quote.buy_rate  # type: ignore[attr-defined]
    tx.sell_rate = quote.sell_rate  # type: ignore[attr-defined]
    tx.profit_pct = quote.profit_pct  # type: ignore[attr-defined]
