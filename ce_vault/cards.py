"""Premium card renderers — one card per message, never mixed."""

from __future__ import annotations

import html
from typing import Iterable

from ce_vault import PRODUCT, TAGLINE
from ce_vault.models import ReceiverProfile, Transaction, today_label
from ce_vault.theme import RULE, confidence_tone, status_pipeline
from ce_vault.theme import TxStatus


def _e(value: object) -> str:
    return html.escape(str(value))


def _mono(value: object) -> str:
    """Monospace every money / crypto / numeric figure."""
    return f"<code>{_e(value)}</code>"


def _fmt_thb(amount: float) -> str:
    return f"{amount:,.2f}"


def _fmt_usdt(amount: float) -> str:
    return f"{amount:,.4f}"


def _fmt_rate(rate: float) -> str:
    return f"{rate:,.2f}"


def _fmt_pct(pct: float) -> str:
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


def _fmt_confidence(value: float) -> str:
    return f"{value:.1f}%"


def _row(label: str, value: str, *, mono: bool = False) -> str:
    rendered = _mono(value) if mono else _e(value)
    return f"<b>{_e(label)}</b>\n{rendered}"


def _header(ledger_id: str | None = None, subtitle: str | None = None) -> str:
    lines = [
        f"<b>{PRODUCT}</b>",
        f"<i>{_e(subtitle or TAGLINE)}</i>",
    ]
    if ledger_id:
        lines.append(f"Ledger ID  {_mono(ledger_id)}")
    lines.append(RULE)
    return "\n".join(lines)


def _kv_block(pairs: Iterable[tuple[str, str, bool]]) -> str:
    """pairs: (label, value, use_mono)"""
    chunks: list[str] = []
    for label, value, use_mono in pairs:
        chunks.append(_row(label, value, mono=use_mono))
    return "\n\n".join(chunks)


def loading_card(phase: str = "PROCESSING") -> str:
    return "\n".join(
        [
            _header(subtitle="Operations Console"),
            f"◌ <b>{_e(phase)}</b>",
            "",
            "<i>Updating ledger…</i>",
        ]
    )


def receive_card(tx: Transaction) -> str:
    """Inbound receive / confirmation decision screen."""
    body = _kv_block(
        [
            ("THB", _fmt_thb(tx.thb), True),
            ("USDT", _fmt_usdt(tx.usdt), True),
            ("Buy Rate", _fmt_rate(tx.buy_rate), True),
            ("Sell Rate", _fmt_rate(tx.sell_rate), True),
            ("Profit", _fmt_pct(tx.profit_pct), True),
            ("Receiver", tx.receiver_display, False),
            ("Confidence", _fmt_confidence(tx.confidence), True),
        ]
    )
    return "\n".join(
        [
            _header(tx.ledger_id),
            status_pipeline(tx.status),
            RULE,
            body,
            RULE,
            "<i>Confirm · Edit · Cancel</i>",
        ]
    )


def ocr_card(tx: Transaction) -> str:
    ocr = tx.ocr or {}
    name = ocr.get("receiver_name") or tx.receiver_name or "—"
    bank = ocr.get("bank") or tx.bank or "—"
    last4 = ocr.get("last4") or tx.last4 or "—"
    amount = float(ocr.get("amount_thb") or tx.thb or 0)
    conf = float(ocr.get("confidence") or tx.confidence or 0)
    verified = bool(ocr.get("verified")) or conf >= 90
    status = "Verified" if verified else "Review"
    tone = confidence_tone(conf)
    conf_line = _fmt_confidence(conf)
    if tone == "WARN":
        conf_line = f"{conf_line}  ·  WARN"

    body = _kv_block(
        [
            ("Vision", conf_line, True),
            ("Receiver", name, False),
            ("Bank", bank, False),
            ("Last4", last4, True),
            ("Detected Amount", _fmt_thb(amount), True),
            ("Status", status, False),
        ]
    )
    return "\n".join(
        [
            _header(tx.ledger_id, subtitle="Vision OCR"),
            status_pipeline(TxStatus.OCR_VERIFIED if verified else TxStatus.RECEIVED),
            RULE,
            body,
        ]
    )


def confirmation_card(tx: Transaction) -> str:
    """Alias layout for the confirm decision — same metrics, decision framing."""
    return receive_card(tx)


def success_card(tx: Transaction, balance_usdt: float | None = None) -> str:
    bal = balance_usdt if balance_usdt is not None else tx.usdt
    return "\n".join(
        [
            _header(tx.ledger_id),
            "● <b>SETTLED</b>",
            RULE,
            _row("Ledger ID", tx.ledger_id, mono=True),
            "",
            _row("Profit", _fmt_pct(tx.profit_pct), mono=True),
            "",
            _row("Updated Balance", f"{_fmt_usdt(bal)} USDT", mono=True),
            RULE,
            "<b>Done.</b>",
        ]
    )


def history_card(profile: ReceiverProfile) -> str:
    risk = (profile.risk or "LOW").upper()
    first = profile.first_seen[:10] if profile.first_seen else "—"
    last = today_label(profile.last_seen)
    return "\n".join(
        [
            _header(subtitle="Receiver History"),
            _row("Receiver", profile.display, mono=False),
            "",
            _mono(f"{profile.tx_count} Transactions"),
            _mono(f"{_fmt_thb(profile.total_thb)} THB"),
            _mono(f"{_fmt_usdt(profile.total_usdt)} USDT"),
            RULE,
            _row("First Seen", first, mono=False),
            "",
            _row("Last Seen", last, mono=False),
            "",
            _row("Risk", risk, mono=False),
        ]
    )


def error_card(*, problem: str, cause: str, action: str) -> str:
    return "\n".join(
        [
            _header(subtitle="Exception"),
            "● <b>ERROR</b>",
            RULE,
            _row("Problem", problem, mono=False),
            "",
            _row("Cause", cause, mono=False),
            "",
            _row("Action", action, mono=False),
        ]
    )


def edit_card(tx: Transaction) -> str:
    body = _kv_block(
        [
            ("THB", _fmt_thb(tx.thb), True),
            ("USDT", _fmt_usdt(tx.usdt), True),
            ("Receiver", tx.receiver_display, False),
            ("Bank", tx.bank or "—", False),
            ("Last4", tx.last4 or "—", True),
        ]
    )
    return "\n".join(
        [
            _header(tx.ledger_id, subtitle="Edit Entry"),
            status_pipeline(TxStatus.EDITING),
            RULE,
            body,
            RULE,
            "<i>Send corrected THB amount, or tap fields below.</i>",
        ]
    )


def delete_card(tx: Transaction) -> str:
    return "\n".join(
        [
            _header(tx.ledger_id, subtitle="Delete Entry"),
            "● <b>CONFIRM DELETE</b>",
            RULE,
            _row("Ledger ID", tx.ledger_id, mono=True),
            "",
            _row("Receiver", tx.receiver_display, mono=False),
            "",
            _row("THB", _fmt_thb(tx.thb), mono=True),
            RULE,
            "<i>This removes the entry from the active ledger.</i>",
        ]
    )


def console_home(*, balance_usdt: float, open_count: int, settled_today: int) -> str:
    return "\n".join(
        [
            _header(subtitle="Operations Console"),
            _row("Vault Balance", f"{_fmt_usdt(balance_usdt)} USDT", mono=True),
            "",
            _row("Open", str(open_count), mono=True),
            "",
            _row("Settled Today", str(settled_today), mono=True),
            RULE,
            "<i>Send a slip photo — or a USDT amount.</i>",
        ]
    )
