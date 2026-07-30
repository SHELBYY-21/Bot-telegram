"""Number and money formatting — always monospace in the UI layer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def money(value: float | int | None, places: int = 2) -> str:
    if value is None:
        return "—"
    return f"{float(value):,.{places}f}"


def crypto(value: float | int | None, places: int = 4) -> str:
    if value is None:
        return "—"
    return f"{float(value):,.{places}f}"


def pct(value: float | int | None, places: int = 2, signed: bool = True) -> str:
    if value is None:
        return "—"
    v = float(value)
    if signed:
        return f"{v:+.{places}f}%"
    return f"{v:.{places}f}%"


def confidence(value: float | int | None) -> str:
    if value is None:
        return "—"
    return f"{float(value):.1f}%"


def mask_account(last4: str | None, bank: str | None = None) -> str:
    digits = (last4 or "????")[-4:].rjust(4, "•")
    bank_part = (bank or "BANK").upper()
    return f"{bank_part} ••••{digits}"


def ledger_id(now: datetime | None = None, seq: int = 1) -> str:
    ts = now or datetime.now(timezone.utc)
    return f"LV-{ts.strftime('%Y%m%d')}-{seq:04d}"


def when(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    today = datetime.now(timezone.utc).date()
    if dt.astimezone(timezone.utc).date() == today:
        return "Today"
    return dt.strftime("%Y-%m-%d")


def coalesce(*values: Any, default: str = "—") -> str:
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return default
