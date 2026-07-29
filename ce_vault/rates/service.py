"""Automatic rate engine — staff never enters Buy Rate."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from ce_vault.theme import to_decimal


@dataclass(frozen=True)
class Quote:
    thb: Decimal
    usdt: Decimal
    buy_rate: Decimal
    sell_rate: Decimal
    profit_pct: Decimal


def profit_pct(buy_rate: Decimal, sell_rate: Decimal) -> Decimal:
    buy = to_decimal(buy_rate)
    sell = to_decimal(sell_rate)
    if buy <= 0:
        return Decimal("0")
    return ((sell - buy) / buy * Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def quote_from_thb(thb: Decimal, buy_rate: Decimal, sell_rate: Decimal) -> Quote:
    """USDT = THB / Sell Rate. Buy Rate is system-owned."""
    thb = to_decimal(thb)
    buy = to_decimal(buy_rate)
    sell = to_decimal(sell_rate)
    if sell <= 0:
        raise ValueError("sell_rate must be positive")
    usdt = (thb / sell).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return Quote(
        thb=thb.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        usdt=usdt,
        buy_rate=buy.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        sell_rate=sell.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        profit_pct=profit_pct(buy, sell),
    )


def quote_from_usdt(usdt: Decimal, buy_rate: Decimal, sell_rate: Decimal) -> Quote:
    """THB = USDT * Sell Rate."""
    usdt = to_decimal(usdt)
    buy = to_decimal(buy_rate)
    sell = to_decimal(sell_rate)
    thb = (usdt * sell).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return Quote(
        thb=thb,
        usdt=usdt.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
        buy_rate=buy.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        sell_rate=sell.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        profit_pct=profit_pct(buy, sell),
    )


class RateService:
    """Thin facade over ledger meta rates."""

    def __init__(self, store):
        self.store = store

    def current(self) -> tuple[Decimal, Decimal]:
        return self.store.get_rates()

    def set(
        self, buy: Decimal | None = None, sell: Decimal | None = None
    ) -> tuple[Decimal, Decimal]:
        cur_buy, cur_sell = self.store.get_rates()
        new_buy = to_decimal(buy) if buy is not None else cur_buy
        new_sell = to_decimal(sell) if sell is not None else cur_sell
        if new_buy <= 0 or new_sell <= 0:
            raise ValueError("rates must be positive")
        self.store.set_rates(new_buy, new_sell)
        return new_buy, new_sell

    def from_thb(self, thb: Decimal) -> Quote:
        buy, sell = self.current()
        return quote_from_thb(thb, buy, sell)

    def from_usdt(self, usdt: Decimal) -> Quote:
        buy, sell = self.current()
        return quote_from_usdt(usdt, buy, sell)
