"""Transaction confirmation card."""

from __future__ import annotations

from typing import Any

from cards.base import SEP, esc, header, money, pct, receiver_display, status_line


def confirmation_card(tx: dict[str, Any], ocr: dict[str, Any] | None = None) -> str:
    ocr = ocr or tx.get("ocr_data") or {}
    active_status = tx.get("status", "OCR_VERIFIED")
    if active_status == "WAITING_USDT":
        active = "WAITING_USDT"
    elif active_status in ("OCR_VERIFIED", "RECEIVED"):
        active = "OCR_VERIFIED"
    else:
        active = active_status

    bank = ocr.get("bank")
    last4 = ocr.get("last4")
    confidence = ocr.get("confidence") or tx.get("ocr_confidence")

    lines = [
        header(tx.get("id")),
        "",
        status_line(active),
        "",
        "THB",
        money(tx.get("thb"), "THB"),
        "",
        "USDT",
        money(tx.get("usdt"), "USDT"),
        "",
        "Buy Rate",
        money(tx.get("buy_rate")),
        "",
        "Sell Rate",
        money(tx.get("sell_rate")),
        "",
        "Profit",
        pct(tx.get("profit_pct")),
        "",
        "Receiver",
        receiver_display(bank, last4),
    ]

    if confidence:
        lines.extend(["", "Confidence", money(confidence)])

    lines.append(SEP)
    return "\n".join(lines)
