"""CE VAULT operation handlers — slip intake, USDT quote, ledger actions."""

from __future__ import annotations

import logging
import re

from telegram import Update
from telegram.ext import ContextTypes

from ce_vault import cards, keyboards, rates
from ce_vault.design import LedgerStatus
from ce_vault.ledger import Ledger
from ce_vault.messaging import send_card, show_typing, track_console_message
from ce_vault.ocr import (
    format_receiver_display,
    parse_text_slip,
    run_vision_ocr,
    slip_hash,
)

logger = logging.getLogger("ce_vault.handlers")


def get_ledger(context: ContextTypes.DEFAULT_TYPE) -> Ledger:
    return context.application.bot_data["ledger"]


def _staff(update: Update) -> tuple[int | None, str | None]:
    user = update.effective_user
    if not user:
        return None, None
    return user.id, user.full_name or user.username


def _receiver_line(entry: dict) -> str:
    return format_receiver_display(
        entry.get("bank") or "UNK",
        entry.get("last4") or "0000",
        entry.get("receiver"),
    )


async def cmd_console_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = await send_card(update, cards.console_home_card())
    track_console_message(context, msg)


async def cmd_rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sell = rates.configured_sell_rate()
    buy = rates.buy_rate_from_sell(sell)
    profit = rates.profit_pct(buy, sell)
    text = cards.header(subtitle="Rate Board") + "\n\n"
    text += cards.row("Buy Rate", cards.mono(cards.money(buy))) + "\n\n"
    text += cards.row("Sell Rate", cards.mono(cards.money(sell))) + "\n\n"
    text += cards.row("Spread", cards.mono(cards.pct(profit))) + "\n\n"
    text += cards.divider()
    await send_card(update, text)


async def cmd_usdt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Staff provides USDT amount only — everything else is automatic."""
    await show_typing(update, context)
    if not context.args:
        await send_card(
            update,
            cards.error_card(
                problem="Missing USDT amount",
                cause="Command requires a numeric amount",
                action="Send /usdt <amount>",
            ),
        )
        return
    try:
        amount = float(context.args[0].replace(",", ""))
    except ValueError:
        await send_card(
            update,
            cards.error_card(
                problem="Invalid amount",
                cause=f"Could not parse “{context.args[0]}”",
                action="Send a number, e.g. /usdt 12.5",
            ),
        )
        return
    if amount <= 0:
        await send_card(
            update,
            cards.error_card(
                problem="Invalid amount",
                cause="USDT must be positive",
                action="Send /usdt <amount>",
            ),
        )
        return

    quote = rates.quote_from_usdt(amount)
    staff_id, staff_name = _staff(update)
    entry = get_ledger(context).create(
        staff_id=staff_id,
        staff_name=staff_name,
        chat_id=update.effective_chat.id if update.effective_chat else None,
        status=LedgerStatus.WAITING_USDT,
        thb=quote.thb,
        usdt=quote.usdt,
        buy_rate=quote.buy_rate,
        sell_rate=quote.sell_rate,
        profit=quote.profit_pct,
        receiver="Manual USDT",
        bank="MANUAL",
        last4="----",
        confidence=100.0,
    )
    text = cards.transaction_card(
        ledger_id=entry["ledger_id"],
        thb=quote.thb,
        usdt=quote.usdt,
        buy_rate=quote.buy_rate,
        sell_rate=quote.sell_rate,
        profit_pct=quote.profit_pct,
        receiver="Manual · USDT intake",
        confidence=100.0,
        status=LedgerStatus.WAITING_USDT,
    )
    msg = await send_card(
        update,
        text,
        keyboard=keyboards.confirm_edit_cancel(entry["ledger_id"]),
    )
    get_ledger(context).update(entry["ledger_id"], message_id=msg.message_id)
    track_console_message(context, msg)


async def cmd_ledger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await send_card(
            update,
            cards.error_card(
                problem="Missing Ledger ID",
                cause="No identifier provided",
                action="Send /ledger <id>",
            ),
        )
        return
    entry = get_ledger(context).get(context.args[0].upper())
    if not entry:
        # try as-is
        entry = get_ledger(context).get(context.args[0])
    if not entry:
        await send_card(
            update,
            cards.error_card(
                problem="Ledger not found",
                cause=f"No entry for {context.args[0]}",
                action="Check the ID and retry",
            ),
        )
        return
    await _render_entry_card(update, context, entry)


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await send_card(
            update,
            cards.error_card(
                problem="Missing receiver key",
                cause="Last4 required",
                action="Send /history <last4>",
            ),
        )
        return
    last4 = re.sub(r"\D", "", context.args[0])[-4:].zfill(4)
    ledger = get_ledger(context)
    stats = ledger.receiver_stats(last4)
    if not stats.get("tx_count"):
        await send_card(
            update,
            cards.error_card(
                problem="No history",
                cause=f"No ledger entries for ••••{last4}",
                action="Complete a settlement first",
            ),
        )
        return
    receiver = format_receiver_display(
        stats.get("bank") or "UNK",
        last4,
        stats.get("receiver"),
    )
    text = cards.history_card(
        receiver=receiver,
        tx_count=int(stats["tx_count"]),
        total_thb=float(stats["total_thb"] or 0),
        total_usdt=float(stats["total_usdt"] or 0),
        first_seen=cards.format_today(stats.get("first_seen")),
        last_seen=cards.format_today(stats.get("last_seen")),
        risk=ledger.risk_for(last4),
    )
    await send_card(update, text)


async def cmd_recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = get_ledger(context).recent(5)
    if not rows:
        await send_card(
            update,
            cards.error_card(
                problem="Ledger empty",
                cause="No entries yet",
                action="Send a slip or /usdt <amount>",
            ),
        )
        return
    # One card = one decision — show the latest only; hint for more via /ledger
    await _render_entry_card(update, context, rows[0])


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Slip intake — primary CE VAULT workflow."""
    assert update.effective_message
    await show_typing(update, context)

    loading = await send_card(
        update,
        cards.loading_card("Scanning", "Vision intake in progress."),
    )
    track_console_message(context, loading)

    photo = update.effective_message.photo[-1]
    caption = update.effective_message.caption or ""
    file = await context.bot.get_file(photo.file_id)
    image_bytes = bytes(await file.download_as_bytearray())

    shash = slip_hash(photo.file_unique_id, photo.file_size)
    ledger = get_ledger(context)
    dup = ledger.find_by_slip_hash(shash)

    ocr = await run_vision_ocr(image_bytes, caption=caption or None)
    if ocr.amount <= 0 and caption:
        # caption may carry amount when vision is weak
        parsed = parse_text_slip(caption)
        if parsed.amount > 0:
            ocr.amount = parsed.amount
            if ocr.bank == "UNK":
                ocr.bank = parsed.bank
            if ocr.last4 == "0000":
                ocr.last4 = parsed.last4
            if ocr.receiver in {"Unknown", "Pending review"}:
                ocr.receiver = parsed.receiver
            ocr.confidence = max(ocr.confidence, parsed.confidence - 5)

    quote = rates.quote_from_thb(ocr.amount) if ocr.amount > 0 else rates.quote_from_thb(0)
    staff_id, staff_name = _staff(update)
    repeat = ledger.receiver_seen_count(ocr.last4) > 0 if ocr.last4 != "0000" else False

    entry = ledger.create(
        staff_id=staff_id,
        staff_name=staff_name,
        chat_id=update.effective_chat.id if update.effective_chat else None,
        status=LedgerStatus.OCR_VERIFIED,
        slip_hash=shash,
        slip_file_id=photo.file_id,
        ocr=ocr.to_dict(),
        receiver=ocr.receiver,
        bank=ocr.bank,
        last4=ocr.last4,
        thb=quote.thb,
        usdt=quote.usdt,
        buy_rate=quote.buy_rate,
        sell_rate=quote.sell_rate,
        profit=quote.profit_pct,
        confidence=ocr.confidence,
        message_id=loading.message_id,
        notes="duplicate" if dup else None,
    )

    ocr_text = cards.ocr_card(
        ledger_id=entry["ledger_id"],
        vision=ocr.confidence,
        receiver=ocr.receiver,
        bank=ocr.bank,
        last4=ocr.last4,
        amount=ocr.amount,
        status="Verified" if ocr.confidence >= 90 else "Review",
        duplicate=bool(dup),
        repeat_receiver=repeat,
    )
    await send_card(
        update,
        ocr_text,
        keyboard=keyboards.confirm_edit_cancel(entry["ledger_id"]),
        edit_message=loading,
    )


async def handle_text_slip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """If pending edit, apply it. Returns True if consumed."""
    pending = context.chat_data.get("pending_edit")
    if not pending or not update.effective_message or not update.effective_message.text:
        return False

    ledger_id = pending["ledger_id"]
    field = pending["field"]
    value = update.effective_message.text.strip()
    ledger = get_ledger(context)
    entry = ledger.get(ledger_id)
    if not entry:
        context.chat_data.pop("pending_edit", None)
        await send_card(
            update,
            cards.error_card(
                problem="Ledger not found",
                cause="Edit target missing",
                action="Restart from slip or /usdt",
            ),
        )
        return True

    updates: dict = {}
    try:
        if field == "thb":
            thb = float(value.replace(",", ""))
            quote = rates.quote_from_thb(thb)
            updates.update(
                thb=quote.thb,
                usdt=quote.usdt,
                buy_rate=quote.buy_rate,
                sell_rate=quote.sell_rate,
                profit=quote.profit_pct,
            )
        elif field == "receiver":
            updates["receiver"] = value[:80]
        elif field == "bank":
            updates["bank"] = value.upper()[:16]
        elif field == "last4":
            digits = re.sub(r"\D", "", value)[-4:]
            if len(digits) != 4:
                raise ValueError("need 4 digits")
            updates["last4"] = digits
        else:
            raise ValueError("unknown field")
    except ValueError as e:
        await send_card(
            update,
            cards.error_card(
                problem="Invalid edit",
                cause=str(e),
                action="Send a valid value",
            ),
        )
        return True

    context.chat_data.pop("pending_edit", None)
    entry = ledger.update(ledger_id, **updates)
    assert entry
    await _render_entry_card(update, context, entry, with_actions=True)
    return True


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    data = query.data

    if data == "lv:dismiss":
        return

    parts = data.split(":")
    if len(parts) < 2:
        return
    domain = parts[0]

    if domain == "lv":
        await _ledger_callback(update, context, parts)
    elif domain == "ag":
        await _agent_callback(update, context, parts)


async def _ledger_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    query = update.callback_query
    assert query
    action = parts[1]
    ledger_id = parts[2] if len(parts) > 2 else ""
    ledger = get_ledger(context)

    if action == "editfield" and len(parts) >= 4:
        field = parts[3]
        entry = ledger.get(ledger_id)
        if not entry:
            return
        context.chat_data["pending_edit"] = {"ledger_id": ledger_id, "field": field}
        current = str(entry.get(field) or "—")
        text = cards.edit_card(ledger_id=ledger_id, field=field.upper(), current=current)
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=keyboards.edit_fields(ledger_id),
            disable_web_page_preview=True,
        )
        return

    entry = ledger.get(ledger_id) if ledger_id else None

    if action == "edit":
        if not entry:
            return
        text = cards.edit_card(
            ledger_id=ledger_id,
            field="Select",
            current="—",
            hint="Choose a field below.",
        )
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=keyboards.edit_fields(ledger_id),
            disable_web_page_preview=True,
        )
        return

    if action == "back":
        if entry:
            await _edit_query_entry(query, context, entry, with_actions=True)
        return

    if action == "cancel":
        if entry:
            ledger.update(ledger_id, status=LedgerStatus.CANCELLED)
            text = cards.error_card(
                problem="Cancelled",
                cause=f"Ledger {ledger_id} voided",
                action="Send a new slip when ready",
            )
            await query.edit_message_text(
                text, parse_mode="HTML", disable_web_page_preview=True
            )
        return

    if action == "confirm":
        if not entry:
            return
        # Move to waiting USDT / ready for settle
        if float(entry.get("thb") or 0) <= 0:
            text = cards.error_card(
                problem="Cannot confirm",
                cause="THB amount is zero",
                action="Edit THB, then Confirm",
            )
            await query.edit_message_text(
                text,
                parse_mode="HTML",
                reply_markup=keyboards.edit_fields(ledger_id),
                disable_web_page_preview=True,
            )
            return
        entry = ledger.update(ledger_id, status=LedgerStatus.WAITING_USDT)
        assert entry
        text = cards.transaction_card(
            ledger_id=ledger_id,
            thb=float(entry["thb"] or 0),
            usdt=float(entry["usdt"] or 0),
            buy_rate=float(entry["buy_rate"] or 0),
            sell_rate=float(entry["sell_rate"] or 0),
            profit_pct=float(entry["profit"] or 0),
            receiver=_receiver_line(entry),
            confidence=entry.get("confidence"),
            status=LedgerStatus.WAITING_USDT,
        )
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=keyboards.settle_waiting(ledger_id),
            disable_web_page_preview=True,
        )
        return

    if action == "settle":
        if not entry:
            return
        entry = ledger.update(ledger_id, status=LedgerStatus.SETTLED)
        assert entry
        bal = ledger.settled_balance()
        text = cards.success_card(
            ledger_id=ledger_id,
            profit_pct=float(entry.get("profit") or 0),
            balance_usdt=bal["usdt"],
        )
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=keyboards.done_only(),
            disable_web_page_preview=True,
        )
        return

    if action == "delete":
        if entry and ledger.delete(ledger_id):
            text = cards.error_card(
                problem="Deleted",
                cause=f"Ledger {ledger_id} removed",
                action="No further action",
            )
            await query.edit_message_text(
                text, parse_mode="HTML", disable_web_page_preview=True
            )
        return

    if action == "keep":
        if entry:
            await _edit_query_entry(query, context, entry, with_actions=True)
        return


async def _agent_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    """Agent inline actions — deferred to bot module via bot_data hook."""
    query = update.callback_query
    assert query
    action = parts[1]
    agent_id = parts[2] if len(parts) > 2 else ""
    handler = context.application.bot_data.get("agent_callback_handler")
    if handler:
        await handler(update, context, action, agent_id)


async def _render_entry_card(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    entry: dict,
    *,
    with_actions: bool = False,
) -> None:
    status_raw = entry.get("status") or LedgerStatus.RECEIVED.value
    try:
        status = LedgerStatus(status_raw)
    except ValueError:
        status = LedgerStatus.RECEIVED

    if status == LedgerStatus.SETTLED:
        bal = get_ledger(context).settled_balance()
        text = cards.success_card(
            ledger_id=entry["ledger_id"],
            profit_pct=float(entry.get("profit") or 0),
            balance_usdt=bal["usdt"],
        )
        kb = None
    elif status == LedgerStatus.OCR_VERIFIED:
        text = cards.ocr_card(
            ledger_id=entry["ledger_id"],
            vision=float(entry.get("confidence") or 0),
            receiver=entry.get("receiver") or "—",
            bank=entry.get("bank") or "—",
            last4=entry.get("last4") or "—",
            amount=float(entry.get("thb") or 0),
        )
        kb = keyboards.confirm_edit_cancel(entry["ledger_id"]) if with_actions else None
    else:
        text = cards.transaction_card(
            ledger_id=entry["ledger_id"],
            thb=float(entry.get("thb") or 0),
            usdt=float(entry.get("usdt") or 0),
            buy_rate=float(entry.get("buy_rate") or 0),
            sell_rate=float(entry.get("sell_rate") or 0),
            profit_pct=float(entry.get("profit") or 0),
            receiver=_receiver_line(entry),
            confidence=entry.get("confidence"),
            status=status if status in LedgerStatus else LedgerStatus.WAITING_USDT,
        )
        kb = (
            keyboards.confirm_edit_cancel(entry["ledger_id"])
            if with_actions and status != LedgerStatus.WAITING_USDT
            else keyboards.settle_waiting(entry["ledger_id"])
            if with_actions
            else None
        )

    msg = await send_card(update, text, keyboard=kb)
    track_console_message(context, msg)


async def _edit_query_entry(query, context, entry: dict, *, with_actions: bool) -> None:
    # Reuse render logic via fabricating from entry fields
    status_raw = entry.get("status") or LedgerStatus.WAITING_USDT.value
    try:
        status = LedgerStatus(status_raw)
    except ValueError:
        status = LedgerStatus.WAITING_USDT

    text = cards.transaction_card(
        ledger_id=entry["ledger_id"],
        thb=float(entry.get("thb") or 0),
        usdt=float(entry.get("usdt") or 0),
        buy_rate=float(entry.get("buy_rate") or 0),
        sell_rate=float(entry.get("sell_rate") or 0),
        profit_pct=float(entry.get("profit") or 0),
        receiver=_receiver_line(entry),
        confidence=entry.get("confidence"),
        status=status,
    )
    kb = None
    if with_actions:
        if status == LedgerStatus.WAITING_USDT:
            kb = keyboards.settle_waiting(entry["ledger_id"])
        else:
            kb = keyboards.confirm_edit_cancel(entry["ledger_id"])
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=kb,
        disable_web_page_preview=True,
    )


async def cmd_delete_ledger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await send_card(
            update,
            cards.error_card(
                problem="Missing Ledger ID",
                cause="No identifier provided",
                action="Send /void <id>",
            ),
        )
        return
    ledger_id = context.args[0]
    entry = get_ledger(context).get(ledger_id) or get_ledger(context).get(ledger_id.upper())
    if not entry:
        await send_card(
            update,
            cards.error_card(
                problem="Ledger not found",
                cause=f"No entry for {ledger_id}",
                action="Check the ID",
            ),
        )
        return
    text = cards.delete_card(
        ledger_id=entry["ledger_id"],
        receiver=_receiver_line(entry),
        thb=float(entry.get("thb") or 0),
        usdt=float(entry.get("usdt") or 0),
    )
    await send_card(
        update,
        text,
        keyboard=keyboards.delete_confirm(entry["ledger_id"]),
    )
