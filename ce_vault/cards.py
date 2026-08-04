"""CE VAULT card renderers.

Design language (see the CE VAULT OS brief):
  - One card = one decision. No paragraphs.
  - Boxed title on every card. UPPERCASE headings, Title Case body,
    monospace numbers, small italic labels.
  - Section stack: LABEL / <blank> / value — one concept per section.
  - Divider between sections. No emoji. No duplicate information.
"""

from __future__ import annotations

from typing import Any

from ce_vault.typography import (
    BADGE_MAP,
    bank_receiver,
    boxed_title,
    divider,
    esc,
    label,
    money,
    money_signed,
    mono,
    pct,
    risk_level,
    section,
    status_badge,
)


BRAND_TITLE = "CE VAULT"
BRAND_SUBTITLE = "Financial Operations"


def _footer_ledger(ledger_id: str) -> list[str]:
    """The ``#CE-YYYYMMDD-XXXX`` ledger reference at the bottom of tx cards."""
    return [divider(), label("Ledger"), mono(f"#{ledger_id}")]


def _format_slip_date(iso: str | None) -> tuple[str, str] | None:
    """Split ISO slip datetime into ("12 Jul 2026", "11:06") — mockup shape."""
    if not iso:
        return None
    from datetime import datetime

    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.strftime("%d %b %Y"), dt.strftime("%H:%M")


def header(ledger_id: str | None = None, subtitle: str = BRAND_SUBTITLE) -> str:
    """Legacy header used by /console_home and by any test that still asserts
    on this shape. New cards should use boxed_title(...) directly.
    """
    title = boxed_title(BRAND_TITLE, subtitle=subtitle)
    if not ledger_id:
        return title
    return "\n".join([title, mono(ledger_id), divider()])


# --- 1. OCR VERIFIED -----------------------------------------------------

def ocr_card(
    *,
    ledger_id: str,
    confidence: float,
    receiver_name: str | None,
    bank: str | None,
    last4: str | None,
    amount: float | None,
    slip_datetime: str | None = None,
    verified: bool = True,
    warn: bool = False,
    duplicate: bool = False,
    repeat_receiver: bool = False,
    repeat_count: int = 0,
) -> str:
    """Card 1 — OCR VERIFIED.

    Renders the AMOUNT / RECEIVER / DATE / NEXT stack from the mockup.
    Alerts (duplicate slip, low confidence, repeat receiver) collapse into
    a single review-badge line so we don't accumulate a paragraph.
    """
    if duplicate or warn:
        badge_status = "REVIEW"
    else:
        badge_status = "VERIFIED" if verified else "REVIEW"
    conf_str = f"{float(confidence):.1f}%" if confidence is not None else "—"

    blocks: list[str] = [
        boxed_title(BRAND_TITLE, subtitle=BRAND_SUBTITLE),
        status_badge(badge_status, right=conf_str),
        divider(),
        section("AMOUNT", f"{money(amount or 0, 2)} THB" if amount else "—"),
    ]

    receiver_extra = None
    if receiver_name:
        receiver_extra = receiver_name
    blocks += [divider(), section("RECEIVER", bank_receiver(bank, last4), extra=receiver_extra)]

    date_parts = _format_slip_date(slip_datetime)
    if date_parts:
        d, t = date_parts
        blocks += [divider(), section("DATE", d, extra=t)]

    # NEXT — one decision: enter the USDT actually sent.
    blocks += [divider(), section("NEXT", "Enter USDT Amount")]

    # Review reasons folded under the badge — expose only if non-obvious.
    reasons: list[str] = []
    if duplicate:
        reasons.append("Duplicate slip")
    if warn:
        reasons.append("OCR confidence low")
    if repeat_receiver and not duplicate:
        reasons.append(f"Known receiver · {repeat_count} prior")
    if reasons:
        blocks += [divider(), label("Notes"), esc(" · ".join(reasons))]

    blocks += _footer_ledger(ledger_id)
    return "\n".join(blocks)


# --- 2. WAITING FOR USDT (Transaction Preview) ---------------------------

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
    status: str = "WAITING USDT",
    hint: str | None = None,
) -> str:
    """Card 2 — Transaction Preview / Waiting for USDT.

    Rendered after the operator hits Continue on OCR VERIFIED. USDT is
    "Waiting..." and Buy Rate is "—" until the operator sends the number.
    """
    blocks = [
        boxed_title("Transaction Preview"),
        section("THB", money(thb or 0, 2) if thb is not None else "—"),
        "",
        section("USDT", money(usdt, 4) if usdt is not None else "Waiting..."),
        "",
        section("Buy Rate", money(buy_rate, 4) if buy_rate else "—"),
        "",
        section("Sell Rate", money(sell_rate or 0, 2) if sell_rate else "—"),
        divider(),
        section("Receiver", bank_receiver(bank, last4)),
        divider(),
        label(hint or "Waiting for settlement…"),
    ]
    blocks += _footer_ledger(ledger_id)
    return "\n".join(blocks)


# --- 3. CONFIRMATION -----------------------------------------------------

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
    history_count: int | None = None,
) -> str:
    """Card 3 — Confirm Transaction.

    Renders full receipt with Estimated Profit as THB (from actuals math),
    plus receiver history count when known. This is the only card with a
    keyboard footer (Confirm / Edit / Cancel), so the profit surface must
    be unambiguous before the operator commits.
    """
    profit_thb = round(float(usdt) * (float(sell_rate) - float(buy_rate)), 2)
    blocks = [
        boxed_title("Confirm Transaction"),
        section("THB", money(thb, 2)),
        "",
        section("USDT", money(usdt, 4)),
        "",
        section("Buy Rate", money(buy_rate, 4)),
        "",
        section("Sell Rate", money(sell_rate, 4)),
        "",
        section("Estimated Profit", f"{money_signed(profit_thb, 2)} THB"),
        divider(),
        section("Receiver", bank_receiver(bank, last4)),
    ]
    if history_count is not None:
        blocks += ["", section("History", f"{history_count} Transactions")]
    blocks += _footer_ledger(ledger_id)
    return "\n".join(blocks)


# --- 4. SUCCESS ----------------------------------------------------------

def success_card(
    *,
    ledger_id: str,
    profit_pct: float | None,
    profit_thb: float | None,
    balance_usdt: float | None = None,
    balance_thb: float | None = None,
    thb: float | None = None,
    usdt: float | None = None,
    buy_rate: float | None = None,
    sell_rate: float | None = None,
    badge: str = "SETTLED",
    closing: str | None = None,  # ignored — kept for signature compat
) -> str:
    """Card 4 — Transaction Settled.

    Renders the final receipt: ledger ref, THB/USDT sent, BUY/SELL rates,
    Profit, Vault Balance. Reads as a permanent record — no further action.
    """
    blocks = [
        boxed_title("Transaction Settled"),
        status_badge(badge),
        divider(),
        label("Ledger"),
        mono(f"#{ledger_id}"),
    ]
    if thb is not None or usdt is not None:
        blocks += [divider()]
        if thb is not None:
            blocks += [section("THB", money(thb, 2)), ""]
        if usdt is not None:
            blocks += [section("USDT", money(usdt, 4))]
    if buy_rate is not None or sell_rate is not None:
        blocks += [divider()]
        if buy_rate is not None:
            blocks += [section("BUY", money(buy_rate, 4)), ""]
        if sell_rate is not None:
            blocks += [section("SELL", money(sell_rate, 4))]
    if profit_thb is not None:
        blocks += [divider(), section("Profit", f"{money_signed(profit_thb, 2)} THB")]
    elif profit_pct is not None:
        blocks += [divider(), section("Profit", pct(profit_pct))]
    if balance_usdt is not None:
        blocks += [divider(), section("Vault Balance", f"{money(balance_usdt, 2)} USDT")]
    if balance_thb is not None and balance_usdt is None:
        blocks += [divider(), section("Vault Balance", f"{money(balance_thb, 2)} THB")]
    return "\n".join(blocks)


# --- 5. RECEIVER PROFILE -------------------------------------------------

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
    """Card 5 — Receiver Intelligence."""
    from ce_vault.typography import format_ts

    risk = risk_level(tx_count, total_thb)
    blocks = [
        boxed_title("Receiver Intelligence"),
        mono(bank_receiver(bank, last4)),
    ]
    if receiver_name:
        blocks += ["", esc(receiver_name)]
    blocks += [
        divider(),
        section("Transactions", str(tx_count)),
        "",
        section("Volume", f"{money(total_thb, 0)} THB"),
        "",
        section("USDT", money(total_usdt, 4)),
        divider(),
        section("First Seen", format_ts(first_seen)),
        "",
        section("Last Seen", format_ts(last_seen)),
        divider(),
        section("Risk", risk),
    ]
    return "\n".join(blocks)


# --- 6. DAILY DASHBOARD --------------------------------------------------

def today_card(
    *,
    summary: dict,
    by_staff: list[dict] | None = None,
    balance_usdt: float | None = None,
    sell_rate: float | None = None,
) -> str:
    """Card 6 — Today.

    Mockup order: Transactions / Volume / Profit, then Pending / Completed,
    then Wallet, then OCR Accuracy. Per-staff totals render below when
    passed — the primary card carries the aggregate.
    """
    tx = int(summary.get("tx_count") or 0)
    pending = int(summary.get("pending") or 0)
    settled = int(summary.get("settled") or 0)
    blocks = [
        boxed_title("Today"),
        section("Transactions", str(tx)),
        "",
        section("Volume", f"{money(float(summary.get('thb') or 0), 0)} THB"),
        "",
        section("Profit", f"{money(float(summary.get('profit_thb') or 0), 0)} THB"),
        divider(),
        section("Pending", str(pending)),
        "",
        section("Completed", str(settled)),
    ]
    if balance_usdt is not None:
        blocks += [divider(), section("Wallet", f"{money(balance_usdt, 2)} USDT")]

    ocr_acc = summary.get("ocr_accuracy")
    if ocr_acc is not None:
        blocks += [divider(), section("OCR Accuracy", f"{float(ocr_acc):.2f}%")]

    if by_staff:
        blocks += [divider(), label("By Staff"), ""]
        for row in by_staff:
            name = esc(str(row.get("staff_name") or "—"))
            n = int(row.get("tx_count") or 0)
            v = money(float(row.get("thb") or 0), 0)
            blocks.append(f"{name}  ·  {mono(str(n))}  ·  {mono(v)}")
    return "\n".join(blocks)


# --- 7. ERROR ------------------------------------------------------------

def error_card(
    *,
    problem: str,
    cause: str | None = None,
    action: str | None = None,
) -> str:
    """Card 7 — Action Required (generic error).

    ``cause`` and ``action`` are optional to keep the card at one message —
    if omitted, the card is just problem + a single hint. See
    duplicate_slip_card for the duplicate-specific variant that carries
    the previous ledger ref.
    """
    blocks = [
        boxed_title("Action Required"),
        mono(problem),
    ]
    if cause:
        blocks += [divider(), section("Cause", cause)]
    if action:
        blocks += [divider(), label(action)]
    return "\n".join(blocks)


def duplicate_slip_card(
    *,
    previous_time: str | None,
    previous_ledger_id: str | None,
) -> str:
    """Card 7 — Duplicate Slip Detected (specific error).

    Kept separate from generic error_card so the "Previous / Ledger"
    section is a first-class block, not a paragraph shoved into `cause`.
    """
    from ce_vault.typography import format_ts

    prev_time = format_ts(previous_time) if previous_time else "—"
    prev_ref = f"#{previous_ledger_id}" if previous_ledger_id else "—"
    return "\n".join(
        [
            boxed_title("Action Required"),
            mono("Duplicate Slip Detected"),
            divider(),
            section("Previous", prev_time),
            "",
            section("Ledger", prev_ref),
            divider(),
            label("Please upload another slip or contact Admin."),
        ]
    )


# --- 8. EDIT -------------------------------------------------------------

def edit_card(
    *,
    ledger_id: str,
    thb: float | None,
    usdt: float | None,
    bank: str | None = None,
    last4: str | None = None,
) -> str:
    """Card 8 — Edit Transaction.

    Shows the current THB/USDT and the reply shorthand. Accepted formats
    (parsed in ocr.parse_edit_command):
        THB 500          →  set THB
        USDT 12.5        →  set USDT
        BANK SCB 3376    →  set bank + last4
        +500             →  shorthand for THB 500
        -12.5U / 12.5U   →  shorthand for USDT 12.5
    """
    blocks = [
        boxed_title("Edit Transaction"),
        label("Current"),
        "",
        section("THB", money(thb or 0, 2)),
        "",
        section("USDT", money(usdt or 0, 4)),
    ]
    if bank or last4:
        blocks += ["", section("Receiver", bank_receiver(bank, last4))]
    blocks += [
        divider(),
        label("Reply with"),
        "",
        mono("THB 500"),
        "",
        mono("USDT 12.5"),
        "",
        label("or shorthand"),
        "",
        mono("+500  -12.5U"),
    ]
    blocks += _footer_ledger(ledger_id)
    return "\n".join(blocks)


# --- misc cards used by existing handlers --------------------------------

def delete_card(*, ledger_id: str, thb: float | None, bank: str | None, last4: str | None) -> str:
    return "\n".join(
        [
            boxed_title("Delete Transaction"),
            section("THB", money(thb or 0, 2)),
            "",
            section("Receiver", bank_receiver(bank, last4)),
            divider(),
            label("This removes the ledger entry permanently."),
        ]
        + _footer_ledger(ledger_id)
    )


def loading_card(*, phase: str = "Processing") -> str:
    return "\n".join(
        [
            boxed_title(phase),
            mono("● ● ●"),
            "",
            label("Working"),
        ]
    )


def progress_card(*, ledger_id: str, status: str, detail: str | None = None) -> str:
    blocks = [
        boxed_title("Transaction"),
        status_badge(status),
    ]
    if detail:
        blocks += [divider(), label(detail)]
    blocks += _footer_ledger(ledger_id)
    return "\n".join(blocks)


def console_home(*, buy_rate: float, sell_rate: float, balance_usdt: float) -> str:
    return "\n".join(
        [
            boxed_title(BRAND_TITLE, subtitle=BRAND_SUBTITLE),
            section("Buy Rate", money(buy_rate, 2)),
            "",
            section("Sell Rate", money(sell_rate, 2)),
            "",
            section("USDT Float", money(balance_usdt, 4)),
            divider(),
            label("Drop a slip  ·  or send USDT amount"),
        ]
    )


def compact_ledger_line(entry: Any) -> str:
    """Single-line ledger row used in list_recent (`/ledger` output)."""
    lid = entry.get("id") if isinstance(entry, dict) else getattr(entry, "ledger_id", "?")
    thb = entry.get("thb") if isinstance(entry, dict) else getattr(entry, "thb", None)
    status = entry.get("status") if isinstance(entry, dict) else getattr(entry, "status", "")
    bank = entry.get("bank") if isinstance(entry, dict) else getattr(entry, "bank", None)
    last4 = entry.get("last4") if isinstance(entry, dict) else getattr(entry, "last4", None)
    badge = BADGE_MAP.get((status or "").upper(), status or "—")
    amt = money(thb or 0, 2) if thb is not None else "—"
    return f"{mono(f'#{lid}')}  {mono(amt)}  {esc(bank_receiver(bank, last4))}  {esc(badge)}"
