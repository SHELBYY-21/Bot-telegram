"""Telegram handlers — operations console, not a chatbot."""

from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ce_vault import engine
from ce_vault.cards import EditView, ErrorView, console_home, edit_card, error_card
from ce_vault.config import Settings, is_authorized
from ce_vault.rates import RateBook
from ce_vault.status import PipelineStatus
from ce_vault.ui import (
    edit_card as ui_edit,
    kb_confirm,
    kb_delete,
    kb_done,
    kb_usdt_waiting,
    send_card,
    show_typing,
)

logger = logging.getLogger("ce_vault.handlers")


def desk(context: ContextTypes.DEFAULT_TYPE) -> engine.DeskState:
    return context.application.bot_data["desk"]


def settings(context: ContextTypes.DEFAULT_TYPE) -> Settings:
    return context.application.bot_data["settings"]


def _auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    return is_authorized(user.id if user else None, settings(context))


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _auth(update, context):
        return
    d = desk(context)
    open_n = d.store.count_open()
    await send_card(
        update,
        console_home(buy_rate=d.rates.buy_rate, sell_rate=d.rates.sell_rate, open_count=open_n),
    )


async def cmd_rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _auth(update, context):
        return
    d = desk(context)
    if not context.args:
        await send_card(
            update,
            console_home(
                buy_rate=d.rates.buy_rate,
                sell_rate=d.rates.sell_rate,
                open_count=d.store.count_open(),
            ),
        )
        return
    if len(context.args) != 2:
        await send_card(
            update,
            error_card(
                ErrorView(
                    problem="Invalid rates command",
                    cause="Expected /rates <buy> <sell>",
                    action="Example: /rates 39.89 40.00",
                )
            ),
        )
        return
    try:
        buy = Decimal(context.args[0])
        sell = Decimal(context.args[1])
    except InvalidOperation:
        await send_card(
            update,
            error_card(
                ErrorView(
                    problem="Invalid number",
                    cause="Buy/sell rates must be numeric",
                    action="Example: /rates 39.89 40.00",
                )
            ),
        )
        return
    d.rates = RateBook(buy_rate=buy, sell_rate=sell)
    d.store.set_meta("buy_rate", str(buy))
    d.store.set_meta("sell_rate", str(sell))
    await send_card(
        update,
        console_home(buy_rate=buy, sell_rate=sell, open_count=d.store.count_open()),
    )


async def cmd_ledger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _auth(update, context):
        return
    if not context.args:
        await send_card(
            update,
            error_card(
                ErrorView(
                    problem="Ledger ID required",
                    cause="No identifier provided",
                    action="Usage: /ledger LED-…",
                )
            ),
        )
        return
    record = desk(context).store.get(context.args[0].upper())
    if not record:
        await send_card(
            update,
            error_card(
                ErrorView(
                    problem="Not found",
                    cause=f"{context.args[0]} does not exist",
                    action="Check the Ledger ID",
                )
            ),
        )
        return
    card = engine.confirmation_from_record(record)
    kb = None
    if record.status == PipelineStatus.WAITING_USDT.value:
        kb = kb_usdt_waiting(record.id)
    elif record.status not in {
        PipelineStatus.SETTLED.value,
        "CANCELLED",
        "FAILED",
    }:
        kb = kb_confirm(record.id)
    await send_card(update, card, keyboard=kb)


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _auth(update, context):
        return
    if not context.args:
        await send_card(
            update,
            error_card(
                ErrorView(
                    problem="Receiver required",
                    cause="Missing bank last4",
                    action="Usage: /history SCB 3376",
                )
            ),
        )
        return
    if len(context.args) == 1 and ":" in context.args[0]:
        bank, last4 = context.args[0].split(":", 1)
    elif len(context.args) >= 2:
        bank, last4 = context.args[0], context.args[1]
    else:
        bank, last4 = None, context.args[0]
    await send_card(update, engine.history_for(desk(context), bank, last4))


async def cmd_open(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _auth(update, context):
        return
    rows = desk(context).store.list_recent(limit=8)
    open_rows = [r for r in rows if r.status not in ("SETTLED", "CANCELLED", "FAILED")]
    if not open_rows:
        await send_card(
            update,
            error_card(
                ErrorView(
                    problem="No open ledgers",
                    cause="Desk queue is clear",
                    action="Send a slip to create one",
                )
            ),
        )
        return
    # One card = one decision — show the newest open ledger only
    newest = open_rows[0]
    await send_card(
        update,
        engine.confirmation_from_record(newest),
        keyboard=kb_confirm(newest.id),
    )


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _auth(update, context):
        return
    assert update.effective_message and update.effective_user
    await show_typing(update, context)

    msg = await send_card(update, engine.receive())
    photo = update.effective_message.photo[-1]
    tg_file = await context.bot.get_file(photo.file_id)
    image_bytes = bytes(await tg_file.download_as_bytearray())
    caption = update.effective_message.caption

    await ui_edit(msg, engine.progress(None, PipelineStatus.RECEIVED, "Running vision"))

    d = desk(context)
    record, ocr_html, _dup = await engine.intake_slip(
        d,
        image_bytes=image_bytes,
        caption=caption,
        staff_id=update.effective_user.id,
        staff_name=update.effective_user.full_name,
        chat_id=update.effective_chat.id if update.effective_chat else None,
    )
    d.store.update(record.id, message_id=msg.message_id, slip_file_id=photo.file_id)

    await ui_edit(msg, ocr_html)

    # Decision stays on the OCR card — Confirm advances the pipeline
    record = d.store.get(record.id)
    assert record
    if record.thb is None:
        context.user_data["edit_ledger"] = record.id
    await ui_edit(msg, ocr_html, keyboard=kb_confirm(record.id))


async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _auth(update, context):
        return
    assert update.effective_message and update.effective_user
    doc = update.effective_message.document
    if not doc or not (doc.mime_type or "").startswith("image/"):
        return
    await show_typing(update, context)
    msg = await send_card(update, engine.receive())
    tg_file = await context.bot.get_file(doc.file_id)
    image_bytes = bytes(await tg_file.download_as_bytearray())
    await ui_edit(msg, engine.progress(None, PipelineStatus.RECEIVED, "Running vision"))
    d = desk(context)
    record, ocr_html, _ = await engine.intake_slip(
        d,
        image_bytes=image_bytes,
        caption=update.effective_message.caption,
        staff_id=update.effective_user.id,
        staff_name=update.effective_user.full_name,
        chat_id=update.effective_chat.id if update.effective_chat else None,
        mime=doc.mime_type or "image/jpeg",
    )
    d.store.update(record.id, message_id=msg.message_id, slip_file_id=doc.file_id)
    await ui_edit(msg, ocr_html, keyboard=kb_confirm(record.id))
    record = d.store.get(record.id)
    assert record
    if record.thb is None:
        context.user_data["edit_ledger"] = record.id


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _auth(update, context):
        return
    assert update.effective_message and update.effective_user
    text = (update.effective_message.text or "").strip()
    if not text or text.startswith("/"):
        return

    # Edit mode: field=value pairs
    edit_id = context.user_data.get("edit_ledger")
    if edit_id and ("=" in text or ":" in text):
        patch = _parse_patch(text)
        if patch:
            await show_typing(update, context)
            record, card = engine.apply_edit(desk(context), edit_id, patch)
            if record:
                context.user_data.pop("edit_ledger", None)
                await send_card(update, card, keyboard=kb_confirm(record.id))
            else:
                await send_card(update, card)
            return

    usdt = engine.parse_usdt_message(text)
    if usdt is None:
        # Structured slip text without photo (heuristic OCR)
        if _looks_like_slip_text(text):
            await show_typing(update, context)
            msg = await send_card(update, engine.receive())
            d = desk(context)
            record, ocr_html, _ = await engine.intake_slip(
                d,
                image_bytes=None,
                caption=text,
                staff_id=update.effective_user.id,
                staff_name=update.effective_user.full_name,
                chat_id=update.effective_chat.id if update.effective_chat else None,
            )
            await ui_edit(msg, ocr_html)
            record = d.store.get(record.id)
            assert record
            if record.thb is None:
                context.user_data["edit_ledger"] = record.id
            await ui_edit(msg, ocr_html, keyboard=kb_confirm(record.id))
            return
        return

    await show_typing(update, context)
    record, card = engine.intake_usdt(
        desk(context),
        usdt,
        staff_id=update.effective_user.id,
        staff_name=update.effective_user.full_name,
        chat_id=update.effective_chat.id if update.effective_chat else None,
    )
    await send_card(update, card, keyboard=kb_usdt_waiting(record.id))


def _looks_like_slip_text(text: str) -> bool:
    keys = ("บาท", "THB", "SCB", "KBANK", "บัญชี", "โอน", "Amount", "Receiver")
    return any(k.lower() in text.lower() for k in keys) or bool(re.search(r"\d+\.\d{2}", text))


def _parse_patch(text: str) -> dict[str, str]:
    patch: dict[str, str] = {}
    parts = re.split(r"[,\n]+", text)
    for part in parts:
        if "=" in part:
            k, v = part.split("=", 1)
        elif ":" in part:
            k, v = part.split(":", 1)
        else:
            continue
        patch[k.strip()] = v.strip()
    return patch


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _auth(update, context):
        return
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    data = query.data
    if data == "done":
        if query.message:
            await query.message.edit_reply_markup(reply_markup=None)
        return

    action, _, ledger_id = data.partition(":")
    if not ledger_id:
        return
    d = desk(context)
    record = d.store.get(ledger_id)
    if not record:
        if query.message:
            await ui_edit(
                query.message,
                error_card(
                    ErrorView(
                        problem="Ledger missing",
                        cause=f"{ledger_id} not found",
                        action="Restart from a new slip",
                    )
                ),
            )
        return

    if action == "cf":
        # Confirm OCR → show transaction card, waiting USDT
        if record.thb is None:
            context.user_data["edit_ledger"] = ledger_id
            assert query.message
            await ui_edit(
                query.message,
                edit_card(
                    EditView(
                        ledger_id=ledger_id,
                        fields={
                            "THB": "—",
                            "Receiver": record.receiver_name or "—",
                            "Bank": record.bank or "—",
                            "Last4": record.last4 or "—",
                        },
                    )
                ),
            )
            return
        record = d.store.update(ledger_id, status=PipelineStatus.WAITING_USDT.value)
        card = engine.confirmation_from_record(record)
        assert query.message
        await ui_edit(query.message, card, keyboard=kb_usdt_waiting(ledger_id))
        return

    if action == "st":
        _, card = engine.settle(d, ledger_id)
        assert query.message
        await ui_edit(query.message, card, keyboard=kb_done())
        return

    if action == "ed":
        context.user_data["edit_ledger"] = ledger_id
        assert query.message
        await ui_edit(
            query.message,
            edit_card(
                EditView(
                    ledger_id=ledger_id,
                    fields={
                        "THB": record.thb or "—",
                        "USDT": record.usdt or "—",
                        "Receiver": record.receiver_name or "—",
                        "Bank": record.bank or "—",
                        "Last4": record.last4 or "—",
                    },
                )
            ),
        )
        return

    if action == "cx":
        _, card = engine.cancel(d, ledger_id)
        assert query.message
        await ui_edit(query.message, card)
        return

    if action == "kp":
        assert query.message
        await ui_edit(
            query.message,
            engine.confirmation_from_record(record),
            keyboard=kb_confirm(ledger_id),
        )
        return

    if action == "dd":
        d.store.delete(ledger_id)
        assert query.message
        await ui_edit(
            query.message,
            error_card(
                ErrorView(
                    problem="Ledger deleted",
                    cause=f"{ledger_id} removed from store",
                    action="Send a slip to create a new entry",
                )
            ),
        )


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _auth(update, context):
        return
    if not context.args:
        await send_card(
            update,
            error_card(
                ErrorView(
                    problem="Ledger ID required",
                    cause="Nothing to delete",
                    action="Usage: /delete LED-…",
                )
            ),
        )
        return
    lid = context.args[0].upper()
    card = engine.prepare_delete(desk(context), lid)
    if not card:
        await send_card(
            update,
            error_card(
                ErrorView(
                    problem="Not found",
                    cause=f"{lid} does not exist",
                    action="Check the Ledger ID",
                )
            ),
        )
        return
    # Use dl confirm then operator presses Delete — wire Delete button to actually delete
    await send_card(update, card, keyboard=kb_delete(lid))


def build_handlers() -> list:
    return [
        CommandHandler(["start", "help", "console"], cmd_start),
        CommandHandler("rates", cmd_rates),
        CommandHandler("ledger", cmd_ledger),
        CommandHandler("history", cmd_history),
        CommandHandler("open", cmd_open),
        CommandHandler("delete", cmd_delete),
        CallbackQueryHandler(on_callback),
        MessageHandler(filters.PHOTO, on_photo),
        MessageHandler(filters.Document.IMAGE, on_document),
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_text),
    ]
