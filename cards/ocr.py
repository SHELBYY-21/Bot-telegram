"""OCR result card."""

from __future__ import annotations

from typing import Any

from cards.base import SEP, WARN, esc, header, mono, receiver_display


def ocr_card(tx: dict[str, Any], ocr: dict[str, Any]) -> str:
    ledger_id = tx.get("id", "")
    confidence = ocr.get("confidence", 0)
    warn = confidence < 90

    lines = [
        header(ledger_id),
        "",
        "Vision",
        mono(f"{confidence:.1f}%"),
    ]
    if warn:
        lines.append(f"{WARN} Below 90% threshold")

    lines.extend([
        "",
        "Receiver",
        esc(ocr.get("receiver_name") or "—"),
        "",
        "Bank",
        esc(ocr.get("bank") or "—"),
        "",
        "Last4",
        mono(ocr.get("last4") or "—"),
        "",
        "Detected Amount",
        mono(f"{ocr.get('amount', 0):,.2f}" if ocr.get("amount") else "—"),
        "",
        "Status",
        "<b>Verified</b>" if not warn else "<b>Review Required</b>",
    ])

    if ocr.get("_known_receiver"):
        lines.extend(["", "<i>Known receiver</i>"])

    if tx.get("_duplicate"):
        lines.extend(["", f"{WARN} Duplicate slip detected"])

    lines.append(SEP)
    return "\n".join(lines)
