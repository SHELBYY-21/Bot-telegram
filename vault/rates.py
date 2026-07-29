"""Rate engine — buy/sell spreads and profit. Never ask staff for buy rate."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_BUY_RATE = float(os.environ.get("DEFAULT_BUY_RATE", "39.89"))
DEFAULT_SELL_RATE = float(os.environ.get("DEFAULT_SELL_RATE", "40.00"))
RATES_FILE = Path(os.environ.get("RATES_FILE", "rates.json"))


def load_rates() -> dict[str, float]:
    if RATES_FILE.exists():
        try:
            data = json.loads(RATES_FILE.read_text())
            return {
                "buy_rate": float(data.get("buy_rate", DEFAULT_BUY_RATE)),
                "sell_rate": float(data.get("sell_rate", DEFAULT_SELL_RATE)),
            }
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return {"buy_rate": DEFAULT_BUY_RATE, "sell_rate": DEFAULT_SELL_RATE}


def save_rates(buy_rate: float, sell_rate: float) -> dict[str, float]:
    data = {"buy_rate": float(buy_rate), "sell_rate": float(sell_rate)}
    RATES_FILE.write_text(json.dumps(data, indent=2))
    return data


def usdt_from_thb(thb: float, sell_rate: float | None = None) -> float:
    """Customer-facing conversion: THB ÷ sell rate."""
    rate = sell_rate if sell_rate is not None else load_rates()["sell_rate"]
    if rate <= 0:
        raise ValueError("sell_rate must be positive")
    return round(float(thb) / float(rate), 4)


def thb_from_usdt(usdt: float, sell_rate: float | None = None) -> float:
    rate = sell_rate if sell_rate is not None else load_rates()["sell_rate"]
    if rate <= 0:
        raise ValueError("sell_rate must be positive")
    return round(float(usdt) * float(rate), 2)


def profit_pct(buy_rate: float, sell_rate: float) -> float:
    if buy_rate <= 0:
        raise ValueError("buy_rate must be positive")
    return round(((float(sell_rate) - float(buy_rate)) / float(buy_rate)) * 100, 2)


def quote(
    *,
    thb: float | None = None,
    usdt: float | None = None,
    buy_rate: float | None = None,
    sell_rate: float | None = None,
) -> dict[str, Any]:
    """Build a full quote from either THB or USDT. Rates are automatic."""
    rates = load_rates()
    buy = float(buy_rate if buy_rate is not None else rates["buy_rate"])
    sell = float(sell_rate if sell_rate is not None else rates["sell_rate"])

    if thb is None and usdt is None:
        raise ValueError("Provide thb or usdt")
    if thb is not None and usdt is None:
        thb_v = round(float(thb), 2)
        usdt_v = usdt_from_thb(thb_v, sell)
    elif usdt is not None and thb is None:
        usdt_v = round(float(usdt), 4)
        thb_v = thb_from_usdt(usdt_v, sell)
    else:
        thb_v = round(float(thb), 2)  # type: ignore[arg-type]
        usdt_v = round(float(usdt), 4)  # type: ignore[arg-type]

    return {
        "thb": thb_v,
        "usdt": usdt_v,
        "buy_rate": buy,
        "sell_rate": sell,
        "profit_pct": profit_pct(buy, sell),
    }
