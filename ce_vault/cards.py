"""Card renderers — one card per message, typography-first."""

from __future__ import annotations

from typing import Any

from ce_vault.config import BRAND, SUBTITLE
from ce_vault.status import render_status_rail
from ce_vault.typography import (
    bank_receiver,
    divider,
    esc,
    label,
    money,
    mono,
    pct,
    relative_or_date,
    risk_level,
    value_row,
)


def header(ledger_id: str | None = None, subtitle: str = SUBTITLE) -> str:
    lines = [
        f"<b>{esc(BRAND)}</b>",
        f"<i>{esc(subtitle)}</i>",
    ]
    if ledger_id:
        lines.append(mono(ledger_id))
    lines.append(divider())
    return "\n".join(lines)


def _gap() -> str:
    return ""


def receive_card(
    *,
    ledger_id: str,
    thb: float | None = None,
    usdt: float | None = None,
    buy_rate: float | None = None,
    sell_rate: float | None = None,
    profit_pct: float | None = None,
    bank: str | None = None,
    last4: str | None = None,
    status: str = "RECEIVED",
    hint: str | None = None,
) -> str:
    blocks = [
        header(ledger_id),
        render_status_rail(status),
        _gap(),
    ]
    if thb is not None:
        blocks.append(value_row("THB", money(thb, 2)))
        blocks.append(_gap())
    if usdt is not None:
        blocks.append(value_row("USDT", money(usdt, 4)))
        blocks.append(_gap())
    if buy_rate is not None:
        blocks.append(value_row("Buy Rate", money(buy_rate, 2)))
        blocks.append(_gap())
    if sell_rate is not None:
        blocks.append(value_row("Sell Rate", money(sell_rate, 2)))
        blocks.append(_gap())
    if profit_pct is not None:
        blocks.append(value_row("Profit", pct(profit_pct)))
        blocks.append(_gap())
    if bank or last4:
        blocks.append(value_row("Receiver", bank_receiver(bank, last4), monospace=False))
        blocks.append(_gap())
    if hint:
        blocks.append(f"<i>{esc(hint)}</i>")
    return "\n".join(b for b in blocks if b is not None)


def ocr_card(
    *,
    ledger_id: str,
    confidence: float,
    receiver_name: str | None,
    bank: str | None,
    last4: str | None,
    amount: float | None,
    verified: bool = True,
    warn: bool = False,
    duplicate: bool = False,
    repeat_receiver: bool = False,
    repeat_count: int = 0,
) -> str:
    status_label = "Verified" if verified else "Review"
    blocks = [
        header(ledger_id, subtitle="Vision"),
        value_row("Vision", f"{money(confidence, 1)}%"),
        _gap(),
        value_row("Receiver", receiver_name or "—", monospace=False),
        _gap(),
        value_row("Bank", (bank or "—").upper(), monospace=False),
        _gap(),
        value_row("Last4", last4 or "————"),
        _gap(),
        value_row("Detected Amount", money(amount or 0, 2)),
        _gap(),
        value_row("Status", status_label, monospace=False),
    ]
    alerts: list[str] = []
    if warn:
        alerts.append("Confidence below threshold")
    if duplicate:
        alerts.append("Duplicate slip detected")
    if repeat_receiver:
        alerts.append(f"Known receiver · {repeat_count} prior")
    if alerts:
        blocks.append(_gap())
        blocks.append(divider())
        for a in alerts:
            blocks.append(f"<b>!</b>  {esc(a)}")
    return "\n".join(blocks)


def confirmation_card(
    *,
    ledger_id: str,
    thb: float,
    usdt: float,
    buy_rate: float,
    sell_rate: float,
    profit_pct: float,
    bank: str | None,
    last4: str | None,
    confidence: float | None = None,
    status: str = "OCR VERIFIED",
) -> str:
    blocks = [
        header(ledger_id),
        render_status_rail(status),
        _gap(),
        value_row("THB", money(thb, 2)),
        _gap(),
        value_row("USDT", money(usdt, 4)),
        _gap(),
        value_row("Buy Rate", money(buy_rate, 2)),
        _gap(),
        value_row("Sell Rate", money(sell_rate, 2)),
        _gap(),
        value_row("Profit", pct(profit_pct)),
        _gap(),
        value_row("Receiver", bank_receiver(bank, last4), monospace=False),
    ]
    if confidence is not None:
        blocks.append(_gap())
        blocks.append(value_row("Confidence", f"{money(confidence, 1)}%"))
    return "\n".join(blocks)


def success_card(
    *,
    ledger_id: str,
    profit_pct: float | None,
    profit_thb: float | None,
    balance_usdt: float | None = None,
    balance_thb: float | None = None,
    badge: str = "SETTLED",
    closing: str = "Done.",
) -> str:
    blocks = [
        header(ledger_id),
        f"<b>● {esc(badge)}</b>",
        _gap(),
        value_row("Ledger ID", ledger_id),
        _gap(),
    ]
    if profit_pct is not None:
        blocks.append(value_row("Profit", pct(profit_pct)))
        blocks.append(_gap())
    if profit_thb is not None:
        blocks.append(value_row("Profit THB", money(profit_thb, 2)))
        blocks.append(_gap())
    if balance_thb is not None or balance_usdt is not None:
        bal_thb = money(balance_thb or 0, 2)
        bal_usdt = money(balance_usdt or 0, 4)
        blocks.append(value_row("Updated Balance", f"{bal_thb} THB · {bal_usdt} USDT"))
        blocks.append(_gap())
    blocks.append(f"<b>{esc(closing)}</b>")
    return "\n".join(blocks)


def history_card(
    *,
    bank: str,
    last4: str,
    tx_count: int,
    total_thb: float,
    total_usdt: float,
    first_seen: str | None,
    last_seen: str | None,
    receiver_name: str | None = None,
) -> str:
    risk = risk_level(tx_count, total_thb)
    blocks = [
        header(subtitle="Receiver History"),
        value_row("Receiver", bank_receiver(bank, last4), monospace=False),
    ]
    if receiver_name:
        blocks.append(_gap())
        blocks.append(value_row("Name", receiver_name, monospace=False))
    blocks.extend(
        [
            _gap(),
            value_row("Volume", f"{tx_count} Transactions", monospace=False),
            _gap(),
            value_row("THB", money(total_thb, 2)),
            _gap(),
            value_row("USDT", money(total_usdt, 4)),
            _gap(),
            value_row("First Seen", relative_or_date(first_seen), monospace=False),
            _gap(),
            value_row("Last Seen", relative_or_date(last_seen), monospace=False),
            _gap(),
            value_row("Risk", risk, monospace=False),
        ]
    )
    return "\n".join(blocks)


def error_card(*, problem: str, cause: str, action: str) -> str:
    return "\n".join(
        [
            header(subtitle="Exception"),
            value_row("Problem", problem, monospace=False),
            _gap(),
            value_row("Cause", cause, monospace=False),
            _gap(),
            value_row("Action", action, monospace=False),
        ]
    )


def edit_card(
    *,
    ledger_id: str,
    thb: float | None,
    usdt: float | None,
    bank: str | None,
    last4: str | None,
) -> str:
    blocks = [
        header(ledger_id, subtitle="Edit"),
        value_row("THB", money(thb or 0, 2)),
        _gap(),
        value_row("USDT", money(usdt or 0, 4)),
        _gap(),
        value_row("Receiver", bank_receiver(bank, last4), monospace=False),
        _gap(),
        label("Send a correction"),
        "\n<code>THB 500</code>  ·  <code>USDT 12.5</code>  ·  <code>BANK SCB 3376</code>",
    ]
    return "\n".join(blocks)


def delete_card(*, ledger_id: str, thb: float | None, bank: str | None, last4: str | None) -> str:
    return "\n".join(
        [
            header(ledger_id, subtitle="Delete"),
            value_row("Ledger ID", ledger_id),
            _gap(),
            value_row("THB", money(thb or 0, 2)),
            _gap(),
            value_row("Receiver", bank_receiver(bank, last4), monospace=False),
            _gap(),
            "<b>This removes the ledger entry permanently.</b>",
        ]
    )


def loading_card(*, phase: str = "Processing") -> str:
    return "\n".join(
        [
            header(subtitle=phase),
            "<code>● ● ●</code>",
            _gap(),
            label("Working"),
        ]
    )


def progress_card(*, ledger_id: str, status: str, detail: str | None = None) -> str:
    blocks = [
        header(ledger_id),
        render_status_rail(status),
    ]
    if detail:
        blocks.append(_gap())
        blocks.append(label(detail))
    return "\n".join(blocks)


def console_home(*, buy_rate: float, sell_rate: float, balance_usdt: float) -> str:
    return "\n".join(
        [
            header(subtitle="Operations Console"),
            value_row("Buy Rate", money(buy_rate, 2)),
            _gap(),
            value_row("Sell Rate", money(sell_rate, 2)),
            _gap(),
            value_row("USDT Float", money(balance_usdt, 4)),
            _gap(),
            divider(),
            label("Drop a slip  ·  or send USDT amount"),
        ]
    )


def today_card(
    *,
    summary: dict,
    by_staff: list[dict] | None = None,
    balance_usdt: float | None = None,
    sell_rate: float | None = None,
) -> str:
    """Mini dashboard: today's counts, sums, profit, pending, wallet."""
    blocks = [
        header(subtitle="Today"),
        value_row("Trades", mono(str(summary.get("tx_count", 0)))),
        _gap(),
        value_row("THB In", money(float(summary.get("thb") or 0), 2)),
        _gap(),
        value_row("USDT Out", money(float(summary.get("usdt") or 0), 4)),
        _gap(),
        value_row("Profit", money(float(summary.get("profit_thb") or 0), 2)),
        _gap(),
        value_row(
            "Pending",
            mono(f"{summary.get('pending', 0)} / {summary.get('tx_count', 0)}"),
        ),
    ]
    if balance_usdt is not None:
        blocks.append(_gap())
        blocks.append(value_row("USDT Float", money(float(balance_usdt), 4)))
    if sell_rate is not None:
        blocks.append(_gap())
        blocks.append(value_row("Sell Rate", money(float(sell_rate), 2)))
    if by_staff:
        blocks.append(_gap())
        blocks.append(divider())
        blocks.append(label("By Staff"))
        blocks.append(_gap())
        for row in by_staff:
            name = esc(str(row.get("staff_name") or "—"))
            count = mono(str(row.get("tx_count", 0)))
            thb = money(float(row.get("thb") or 0), 0)
            blocks.append(f"{name}  ·  {count}  ·  {thb}")
    return "\n".join(blocks)


def compact_ledger_line(entry: Any) -> str:
    lid = entry.get("id") if isinstance(entry, dict) else getattr(entry, "ledger_id", "?")
    thb = entry.get("thb") if isinstance(entry, dict) else getattr(entry, "thb", None)
    status = entry.get("status") if isinstance(entry, dict) else getattr(entry, "status", "")
    bank = entry.get("bank") if isinstance(entry, dict) else getattr(entry, "bank", None)
    last4 = entry.get("last4") if isinstance(entry, dict) else getattr(entry, "last4", None)
    recv = bank_receiver(bank, last4)
    amt = money(thb or 0, 2) if thb is not None else "—"
    return f"{mono(lid)}  {mono(amt)}  {esc(recv)}  {esc(status)}"
