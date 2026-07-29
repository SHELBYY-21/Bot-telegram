"""Single-purpose card renderers.

Every response is ONE card. No paragraphs. Labels small, values large
(monospace). Layout mimics a Bloomberg / Stripe ops console in Telegram HTML.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any, Sequence

from ce_vault.design import (
    AGENT_PIPELINE,
    AGENT_STATUS_MAP,
    BRAND,
    CONFIDENCE_WARN_BELOW,
    STATUS_PIPELINE,
    SUBTITLE,
    LedgerStatus,
)


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else "—"))


def money(value: float | int | str | None, places: int = 2) -> str:
    if value is None or value == "":
        return "—"
    try:
        return f"{float(value):,.{places}f}"
    except (TypeError, ValueError):
        return esc(value)


def crypto(value: float | int | str | None, places: int = 4) -> str:
    return money(value, places)


def pct(value: float | int | str | None, places: int = 2) -> str:
    if value is None or value == "":
        return "—"
    try:
        n = float(value)
        sign = "+" if n > 0 else ""
        return f"{sign}{n:.{places}f}%"
    except (TypeError, ValueError):
        return esc(value)


def mono(value: Any) -> str:
    return f"<code>{esc(value)}</code>"


def label(text: str) -> str:
    return f"<i>{esc(text)}</i>"


def row(lbl: str, value: str) -> str:
    return f"{label(lbl)}\n{value}"


def divider() -> str:
    return "────────────────"


def header(ledger_id: str | None = None, subtitle: str = SUBTITLE) -> str:
    lines = [
        f"<b>{esc(BRAND)}</b>",
        label(subtitle),
    ]
    if ledger_id:
        lines.append(f"{label('Ledger ID')}\n{mono(ledger_id)}")
    lines.append(divider())
    return "\n".join(lines)


def status_rail(
    active: str | LedgerStatus,
    pipeline: Sequence[str | LedgerStatus] = STATUS_PIPELINE,
) -> str:
    """Only the active status glows (●). Completed stay ● dim via plain text; future ○."""
    active_label = active.value if isinstance(active, LedgerStatus) else str(active)
    labels = [p.value if isinstance(p, LedgerStatus) else str(p) for p in pipeline]

    try:
        active_idx = labels.index(active_label)
    except ValueError:
        # Error / cancelled / unknown — show active alone
        return f"● <b>{esc(active_label)}</b>"

    lines: list[str] = []
    for i, name in enumerate(labels):
        if i < active_idx:
            lines.append(f"● {esc(name)}")
        elif i == active_idx:
            lines.append(f"● <b>{esc(name)}</b>")
        else:
            lines.append(f"○ {esc(name)}")
    return "\n".join(lines)


# --- Card: Receive (intake / awaiting confirmation) ----------------------

def receive_card(
    *,
    ledger_id: str,
    thb: float,
    usdt: float,
    buy_rate: float,
    sell_rate: float,
    profit_pct: float,
    receiver: str,
    confidence: float | None = None,
    status: LedgerStatus = LedgerStatus.WAITING_USDT,
) -> str:
    parts = [
        header(ledger_id),
        status_rail(status),
        "",
        row("THB", mono(money(thb))),
        "",
        row("USDT", mono(crypto(usdt))),
        "",
        row("Buy Rate", mono(money(buy_rate))),
        "",
        row("Sell Rate", mono(money(sell_rate))),
        "",
        row("Profit", mono(pct(profit_pct))),
        "",
        row("Receiver", esc(receiver)),
    ]
    if confidence is not None:
        conf_line = mono(f"{confidence:.1f}%")
        if confidence < CONFIDENCE_WARN_BELOW:
            conf_line = f"{conf_line}  ⚠"
        parts.extend(["", row("Confidence", conf_line)])
    parts.extend(["", divider()])
    return "\n".join(parts)


# Alias used by confirmation step (same layout, different status emphasis)
transaction_card = receive_card


# --- Card: OCR -----------------------------------------------------------

def ocr_card(
    *,
    ledger_id: str,
    vision: float,
    receiver: str,
    bank: str,
    last4: str,
    amount: float,
    status: str = "Verified",
    duplicate: bool = False,
    repeat_receiver: bool = False,
) -> str:
    vision_val = mono(f"{vision:.1f}%")
    if vision < CONFIDENCE_WARN_BELOW:
        vision_val = f"{vision_val}  ⚠"
        status = "Review"
    parts = [
        header(ledger_id, subtitle="Vision Intake"),
        status_rail(LedgerStatus.OCR_VERIFIED),
        "",
        row("Vision", vision_val),
        "",
        row("Receiver", esc(receiver)),
        "",
        row("Bank", esc(bank)),
        "",
        row("Last4", mono(last4)),
        "",
        row("Detected Amount", mono(money(amount))),
        "",
        row("Status", esc(status)),
    ]
    if duplicate:
        parts.extend(["", row("Flag", esc("DUPLICATE SLIP"))])
    if repeat_receiver:
        parts.extend(["", row("Flag", esc("KNOWN RECEIVER"))])
    parts.extend(["", divider()])
    return "\n".join(parts)


# --- Card: Confirmation --------------------------------------------------

def confirmation_card(
    *,
    ledger_id: str,
    thb: float,
    usdt: float,
    buy_rate: float,
    sell_rate: float,
    profit_pct: float,
    receiver: str,
) -> str:
    return receive_card(
        ledger_id=ledger_id,
        thb=thb,
        usdt=usdt,
        buy_rate=buy_rate,
        sell_rate=sell_rate,
        profit_pct=profit_pct,
        receiver=receiver,
        status=LedgerStatus.WAITING_USDT,
    )


# --- Card: Success -------------------------------------------------------

def success_card(
    *,
    ledger_id: str,
    profit_pct: float,
    balance_usdt: float | None = None,
    balance_thb: float | None = None,
) -> str:
    parts = [
        header(ledger_id),
        "",
        "<b>● SETTLED</b>",
        "",
        row("Profit", mono(pct(profit_pct))),
    ]
    if balance_usdt is not None:
        parts.extend(["", row("Updated Balance", mono(f"{crypto(balance_usdt)} USDT"))])
    elif balance_thb is not None:
        parts.extend(["", row("Updated Balance", mono(f"{money(balance_thb)} THB"))])
    parts.extend(["", divider(), "", "<b>Done.</b>"])
    return "\n".join(parts)


# --- Card: History -------------------------------------------------------

def history_card(
    *,
    receiver: str,
    tx_count: int,
    total_thb: float,
    total_usdt: float,
    first_seen: str,
    last_seen: str,
    risk: str = "LOW",
) -> str:
    parts = [
        header(subtitle="Receiver History"),
        "",
        row("Receiver", esc(receiver)),
        "",
        row("Volume", mono(f"{tx_count} Transactions")),
        "",
        mono(f"{money(total_thb)} THB"),
        mono(f"{crypto(total_usdt)} USDT"),
        "",
        row("First Seen", esc(first_seen)),
        "",
        row("Last Seen", esc(last_seen)),
        "",
        row("Risk", f"<b>{esc(risk)}</b>"),
        "",
        divider(),
    ]
    return "\n".join(parts)


# --- Card: Error ---------------------------------------------------------

def error_card(*, problem: str, cause: str, action: str) -> str:
    return "\n".join(
        [
            header(subtitle="Exception"),
            "",
            row("Problem", esc(problem)),
            "",
            row("Cause", esc(cause)),
            "",
            row("Action", esc(action)),
            "",
            divider(),
        ]
    )


# --- Card: Edit ----------------------------------------------------------

def edit_card(
    *,
    ledger_id: str,
    field: str,
    current: str,
    hint: str = "Send the new value.",
) -> str:
    return "\n".join(
        [
            header(ledger_id, subtitle="Edit Entry"),
            "",
            row("Field", esc(field)),
            "",
            row("Current", mono(current)),
            "",
            row("Input", esc(hint)),
            "",
            divider(),
        ]
    )


# --- Card: Delete --------------------------------------------------------

def delete_card(*, ledger_id: str, receiver: str, thb: float, usdt: float) -> str:
    return "\n".join(
        [
            header(ledger_id, subtitle="Delete Entry"),
            "",
            row("Receiver", esc(receiver)),
            "",
            row("THB", mono(money(thb))),
            "",
            row("USDT", mono(crypto(usdt))),
            "",
            label("This action is permanent."),
            "",
            divider(),
        ]
    )


# --- Card: Loading / Progress --------------------------------------------

def loading_card(phase: str = "Processing", detail: str = "Stand by.") -> str:
    return "\n".join(
        [
            header(subtitle="Console"),
            "",
            f"<b>● {esc(phase.upper())}</b>",
            "",
            label(detail),
            "",
            divider(),
        ]
    )


def progress_card(*, ledger_id: str, status: LedgerStatus, detail: str = "") -> str:
    parts = [
        header(ledger_id),
        status_rail(status),
    ]
    if detail:
        parts.extend(["", label(detail)])
    parts.extend(["", divider()])
    return "\n".join(parts)


# --- Console home / help -------------------------------------------------

def console_home_card() -> str:
    return "\n".join(
        [
            header(subtitle="Operations Console"),
            "",
            label("Intake"),
            "Send a slip photo — or —",
            f"/usdt {mono('amount')}",
            "",
            label("Ledger"),
            f"/ledger {mono('id')}",
            f"/history {mono('last4')}",
            "/rates",
            "",
            label("Agents"),
            f"/agent {mono('prompt')}",
            "/agents",
            "",
            divider(),
            label("One screen. One decision."),
        ]
    )


# --- Cursor agent cards (backward compatible surface) --------------------

def agent_status_label(raw: str | None) -> str:
    key = str(raw or "UNKNOWN").upper()
    return AGENT_STATUS_MAP.get(key, key)


def agent_card(agent: dict) -> str:
    agent_id = str(agent.get("id", "?"))
    status = agent_status_label(agent.get("status"))
    source = agent.get("source") or {}
    target = agent.get("target") or {}
    name = agent.get("name") or agent_id

    pipeline = AGENT_PIPELINE
    if status in ("ERROR", "STOPPED"):
        rail = f"● <b>{esc(status)}</b>"
    else:
        rail = status_rail(status, pipeline)

    parts = [
        header(agent_id, subtitle="Cloud Agent"),
        rail,
        "",
        row("Name", esc(name)),
    ]
    if source.get("repository"):
        repo = source["repository"].rstrip("/").split("/")[-2:]
        short = "/".join(repo) if len(repo) == 2 else source["repository"]
        parts.extend(["", row("Repository", esc(short))])
    if target.get("branchName"):
        parts.extend(["", row("Branch", mono(target["branchName"]))])
    if target.get("prUrl"):
        parts.extend(["", row("Pull Request", esc(target["prUrl"]))])
    if agent.get("summary"):
        summary = str(agent["summary"])
        if len(summary) > 180:
            summary = summary[:177] + "…"
        parts.extend(["", row("Summary", esc(summary))])
    parts.extend(["", divider()])
    return "\n".join(parts)


def agent_success_card(agent: dict) -> str:
    agent_id = str(agent.get("id", "?"))
    target = agent.get("target") or {}
    parts = [
        header(agent_id, subtitle="Cloud Agent"),
        "",
        "<b>● FINISHED</b>",
        "",
    ]
    if target.get("prUrl"):
        parts.extend([row("Pull Request", esc(target["prUrl"])), ""])
    parts.extend([divider(), "", "<b>Done.</b>"])
    return "\n".join(parts)


def format_today(ts: str | float | None = None) -> str:
    if ts is None:
        return "Today"
    if isinstance(ts, (int, float)):
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d")
    text = str(ts)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if text.startswith(today) or text.lower() in {"today", "just now"}:
        return "Today"
    return text[:10] if len(text) >= 10 else text
