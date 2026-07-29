"""Single-card renderers — one screen, one decision.

Every public function returns ONE card body (HTML). Never mix cards.
"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

from vault.design import (
    RULE,
    crypto,
    field_block,
    header,
    mask_account,
    money,
    mono,
    pct,
    status_rail,
)
from vault.ledger import relative_day

if TYPE_CHECKING:
    from vault.models import OCRResult, ReceiverHistory, Transaction


def _esc(value: object | None, fallback: str = "—") -> str:
    if value is None or value == "":
        return fallback
    return html.escape(str(value))


def receive_card(tx: Transaction, *, progress: str | None = None) -> str:
    """Inbound slip / amount received — awaiting OCR or quote."""
    body = [
        header(tx.ledger_id),
        status_rail(tx.status),
        RULE,
    ]
    if progress:
        body.append(f"<i>{html.escape(progress)}</i>")
    else:
        body.append("Inbound captured.")
        body.append("Running verification…")
    return "\n".join(body)


def ocr_card(tx: Transaction, ocr: OCRResult) -> str:
    conf = money(ocr.confidence, decimals=1)
    warn = ""
    if ocr.below_threshold:
        warn = f"\n\n<b>Confidence below 90%</b>\n{mono(conf + '%')}"
    flags = []
    if ocr.duplicate_slip:
        flags.append("Duplicate slip detected")
    if ocr.repeated_receiver:
        flags.append("Known receiver")
    flag_block = ("\n" + "\n".join(f"· {html.escape(f)}" for f in flags)) if flags else ""

    rows = field_block(
        [
            ("Vision", f"{conf}%", True),
            ("Receiver", _esc(ocr.receiver), False),
            ("Bank", _esc(ocr.bank), False),
            ("Last4", _esc(ocr.last4), True),
            (
                "Detected Amount",
                money(ocr.amount_thb) if ocr.amount_thb is not None else "—",
                True,
            ),
            ("Status", _esc(ocr.status), False),
        ]
    )
    return "\n".join(
        [
            header(tx.ledger_id),
            status_rail(tx.status),
            RULE,
            rows,
            warn,
            flag_block,
        ]
    ).rstrip()


def transaction_card(tx: Transaction) -> str:
    receiver = mask_account(tx.last4, tx.bank) if tx.last4 or tx.bank else _esc(tx.receiver)
    conf = (
        f"{money(tx.ocr_confidence, decimals=1)}%"
        if tx.ocr_confidence is not None
        else "—"
    )
    profit = pct(tx.profit_pct) if tx.profit_pct is not None else "—"
    rows = field_block(
        [
            ("THB", money(tx.thb) if tx.thb is not None else "—", True),
            ("USDT", crypto(tx.usdt) if tx.usdt is not None else "—", True),
            ("Buy Rate", money(tx.buy_rate) if tx.buy_rate is not None else "—", True),
            ("Sell Rate", money(tx.sell_rate) if tx.sell_rate is not None else "—", True),
            ("Profit", profit, True),
            ("Receiver", receiver, False),
            ("Confidence", conf, True),
        ]
    )
    return "\n".join(
        [
            header(tx.ledger_id),
            status_rail(tx.status),
            RULE,
            rows,
        ]
    )


def confirmation_card(tx: Transaction) -> str:
    """Alias layout for confirm decision — same hierarchy, explicit CTA hint."""
    card = transaction_card(tx)
    return card + f"\n{RULE}\nConfirm · Edit · Cancel"


def success_card(
    tx: Transaction,
    *,
    balance_usdt: float | None = None,
) -> str:
    profit = pct(tx.profit_pct) if tx.profit_pct is not None else "—"
    bal = crypto(balance_usdt) if balance_usdt is not None else "—"
    rows = field_block(
        [
            ("Ledger ID", tx.ledger_id, True),
            ("Profit", profit, True),
            ("Updated Balance", f"{bal} USDT", True),
        ]
    )
    return "\n".join(
        [
            header(tx.ledger_id),
            status_rail("SETTLED"),
            RULE,
            "<b>SETTLED</b>",
            "",
            rows,
            "",
            "Done.",
        ]
    )


def history_card(hist: ReceiverHistory) -> str:
    receiver = mask_account(hist.last4, hist.bank)
    volume = "\n".join(
        [
            f"{hist.tx_count} Transactions",
            mono(f"{money(hist.total_thb)} THB"),
            mono(f"{crypto(hist.total_usdt)} USDT"),
        ]
    )
    return "\n".join(
        [
            header(),
            f"Receiver\n{receiver}",
            "",
            volume,
            "",
            f"First Seen\n{relative_day(hist.first_seen)}",
            "",
            f"Last Seen\n{relative_day(hist.last_seen)}",
            "",
            f"Risk\n{mono(hist.risk)}",
        ]
    )

def error_card(*, problem: str, cause: str, action: str, ledger_id: str | None = None) -> str:
    rows = field_block(
        [
            ("Problem", html.escape(problem), False),
            ("Cause", html.escape(cause), False),
            ("Action", html.escape(action), False),
        ]
    )
    return "\n".join(
        [
            header(ledger_id),
            rows,
        ]
    )


def edit_card(tx: Transaction) -> str:
    rows = field_block(
        [
            ("Ledger ID", tx.ledger_id, True),
            ("THB", money(tx.thb) if tx.thb is not None else "—", True),
            ("USDT", crypto(tx.usdt) if tx.usdt is not None else "—", True),
            ("Receiver", _esc(tx.receiver), False),
            ("Bank", _esc(tx.bank), False),
            ("Last4", _esc(tx.last4), True),
        ]
    )
    return "\n".join(
        [
            header(tx.ledger_id),
            status_rail(tx.status),
            RULE,
            "<b>EDIT</b>",
            "",
            rows,
            "",
            "Send correction:",
            mono("thb 500"),
            mono("receiver Name"),
            mono("last4 3376"),
            mono("bank SCB"),
        ]
    )


def delete_card(tx: Transaction) -> str:
    rows = field_block(
        [
            ("Ledger ID", tx.ledger_id, True),
            ("THB", money(tx.thb) if tx.thb is not None else "—", True),
            ("Status", _esc(tx.status), False),
        ]
    )
    return "\n".join(
        [
            header(tx.ledger_id),
            RULE,
            "<b>DELETE</b>",
            "",
            rows,
            "",
            "This removes the ledger entry permanently.",
        ]
    )


def loading_card(ledger_id: str | None = None, phase: str = "Processing") -> str:
    return "\n".join(
        [
            header(ledger_id),
            f"<i>● {html.escape(phase)}</i>",
            "○○○",
        ]
    )


def rates_card(buy_rate: float, sell_rate: float, profit: float) -> str:
    rows = field_block(
        [
            ("Buy Rate", money(buy_rate), True),
            ("Sell Rate", money(sell_rate), True),
            ("Spread", pct(profit), True),
        ]
    )
    return "\n".join([header(), rows])


def balance_card(usdt: float, thb: float) -> str:
    rows = field_block(
        [
            ("USDT Inventory", crypto(usdt), True),
            ("THB Collected", money(thb), True),
        ]
    )
    return "\n".join([header(), rows])
