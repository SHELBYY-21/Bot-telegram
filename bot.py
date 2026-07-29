"""CE VAULT — Premium FinTech Operations Console for Telegram.

Staff provide a transfer slip or USDT amount. Rates, profit, and ledger
entries are computed automatically. One card per screen.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from decimal import Decimal, InvalidOperation

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import allowed_user_ids, confidence_warning_threshold
from vault.cards import CardRenderer
from vault.ledger import LedgerStore
from vault.models import PipelineStatus, TransactionDraft
from vault.ocr import process_slip, slip_hash
from vault.rates import RateEngine
from vault.session import SessionStore

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO
)
logger = logging.getLogger("ce_vault")

USDT_PATTERN = re.compile(r"^\s*(\d+(?:\.\d{1,8})?)\s*(?:usdt)?\s*$", re.I)
LEDGER_PATTERN = re.compile(r"^LDG-\d{8}-\d{4}$", re.I)

CB_CONFIRM = "vault:confirm"
CB_EDIT = "vault:edit"
CB_CANCEL = "vault:cancel"
CB_DELETE_CONFIRM = "vault:delete:yes"
CB_DELETE_CANCEL = "vault:delete:no"
CB_HISTORY = "vault:history"


# --- auth ------------------------------------------------------------------


def authorized(update: Update) -> bool:
    allowed = allowed_user_ids()
    if not allowed:
        return True
    return bool(update.effective_user) and update.effective_user.id in allowed


# --- helpers ---------------------------------------------------------------


def rates(context: ContextTypes.DEFAULT_TYPE) -> RateEngine:
    return context.application.bot_data["rates"]


def ledger(context: ContextTypes.DEFAULT_TYPE) -> LedgerStore:
    return context.application.bot_data["ledger"]


def sessions(context: ContextTypes.DEFAULT_TYPE) -> SessionStore:
    return context.application.bot_data["sessions"]


def cards() -> CardRenderer:
    return CardRenderer()


async def send_card(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    keyboard: InlineKeyboardMarkup | None = None,
    replace: bool = True,
) -> int | None:
    """Send or edit a single active card for this chat."""
    assert update.effective_chat
    session = sessions(context).get(update.effective_chat.id)

    if replace and session.active_message_id:
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=session.active_message_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
            sessions(context).save()
            return session.active_message_id
        except Exception:
            logger.debug("edit failed, sending new card", exc_info=True)

    msg = await context.bot.send_message(
        update.effective_chat.id,
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
    session.active_message_id = msg.message_id
    sessions(context).save()
    return msg.message_id


async def typing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Confirm", callback_data=CB_CONFIRM),
                InlineKeyboardButton("Edit", callback_data=CB_EDIT),
            ],
            [InlineKeyboardButton("Cancel", callback_data=CB_CANCEL)],
        ]
    )


def delete_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Delete", callback_data=CB_DELETE_CONFIRM),
                InlineKeyboardButton("Keep", callback_data=CB_DELETE_CANCEL),
            ]
        ]
    )


def history_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Receiver History", callback_data=CB_HISTORY)]]
    )


def new_draft(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    staff_id: int | None = None,
    source: str = "slip",
) -> TransactionDraft:
    engine = rates(context)
    return TransactionDraft(
        ledger_id=ledger(context).next_ledger_id(),
        thb=Decimal("0.00"),
        usdt=Decimal("0.0000"),
        buy_rate=engine.buy_rate,
        sell_rate=engine.sell_rate,
        staff_id=staff_id,
        source=source,
        status=PipelineStatus.RECEIVED,
    )


async def animate_loading(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    ledger_id: str,
    stages: list[tuple[str, int]],
) -> None:
    for stage, progress in stages:
        await typing(update, context)
        await send_card(
            update,
            context,
            cards().loading_card(ledger_id, stage, progress),
            replace=True,
        )
        await asyncio.sleep(0.35)


# --- flows -----------------------------------------------------------------


async def show_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    engine = rates(context)
    totals = ledger(context).totals()
    text = cards().dashboard_card(
        totals,
        (engine.buy_rate, engine.sell_rate, engine.profit_pct),
    )
    await send_card(update, context, text, replace=False)


async def process_slip_flow(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    image_bytes: bytes,
    file_id: str,
) -> None:
    assert update.effective_user
    session = sessions(context).get(update.effective_chat.id)
    draft = new_draft(
        context,
        staff_id=update.effective_user.id,
        source="slip",
    )
    session.draft = draft
    sessions(context).save()

    await animate_loading(
        update,
        context,
        draft.ledger_id,
        [
            ("Scanning slip", 2),
            ("Extracting fields", 5),
            ("Verifying OCR", 8),
        ],
    )

    digest = slip_hash(image_bytes)
    draft.slip_hash = digest
    draft.slip_file_id = file_id
    draft.duplicate_slip = ledger(context).slip_exists(digest)

    try:
        ocr = await process_slip(image_bytes)
    except Exception as exc:
        logger.exception("OCR failed")
        await send_card(
            update,
            context,
            cards().error_card(
                "OCR failed",
                str(exc),
                "Resend a clearer slip image",
            ),
            replace=True,
        )
        session.clear()
        sessions(context).save()
        return

    engine = rates(context)
    calc = engine.from_thb(ocr.amount_thb)
    draft.thb = calc["thb"]
    draft.usdt = calc["usdt"]
    draft.buy_rate = calc["buy_rate"]
    draft.sell_rate = calc["sell_rate"]
    draft.receiver_name = ocr.receiver_name
    draft.bank = ocr.bank
    draft.last4 = ocr.last4
    draft.ocr_confidence = ocr.confidence
    draft.low_confidence = ocr.confidence < confidence_warning_threshold()
    draft.status = PipelineStatus.OCR_VERIFIED

    history = ledger(context).receiver_history(draft.bank, draft.last4)
    draft.repeated_receiver = history is not None and history.transaction_count > 0

    await send_card(update, context, cards().ocr_card(draft), replace=True)
    await asyncio.sleep(0.4)

    draft.status = PipelineStatus.WAITING_USDT
    session.mode = "confirm"
    sessions(context).save()

    keyboard = confirm_keyboard()
    if history:
        keyboard = InlineKeyboardMarkup(
            [
                *confirm_keyboard().inline_keyboard,
                *history_keyboard().inline_keyboard,
            ]
        )

    await send_card(
        update,
        context,
        cards().transaction_card(draft),
        keyboard=keyboard,
        replace=True,
    )


async def process_usdt_flow(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    usdt_amount: Decimal,
) -> None:
    assert update.effective_user
    session = sessions(context).get(update.effective_chat.id)
    draft = session.draft

    if (
        draft
        and session.mode != "edit"
        and draft.status == PipelineStatus.WAITING_USDT
    ):
        engine = rates(context)
        calc = engine.from_usdt(usdt_amount)
        draft.usdt = calc["usdt"]
        draft.thb = calc["thb"]
        draft.buy_rate = calc["buy_rate"]
        draft.sell_rate = calc["sell_rate"]
        session.mode = "confirm"
        sessions(context).save()
        await send_card(
            update,
            context,
            cards().transaction_card(draft),
            keyboard=confirm_keyboard(),
            replace=True,
        )
        return

    draft = new_draft(
        context,
        staff_id=update.effective_user.id,
        source="usdt",
    )
    engine = rates(context)
    calc = engine.from_usdt(usdt_amount)
    draft.thb = calc["thb"]
    draft.usdt = calc["usdt"]
    draft.buy_rate = calc["buy_rate"]
    draft.sell_rate = calc["sell_rate"]
    draft.status = PipelineStatus.WAITING_USDT
    session.draft = draft
    session.mode = "confirm"
    sessions(context).save()

    await animate_loading(
        update,
        context,
        draft.ledger_id,
        [
            ("Computing THB", 4),
            ("Applying rates", 7),
            ("Ready for review", 10),
        ],
    )

    await send_card(
        update,
        context,
        cards().transaction_card(draft),
        keyboard=confirm_keyboard(),
        replace=True,
    )


async def settle_draft(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = sessions(context).get(update.effective_chat.id)
    draft = session.draft
    if not draft:
        return

    if draft.duplicate_slip:
        await send_card(
            update,
            context,
            cards().error_card(
                "Duplicate slip",
                "This slip was already settled",
                "Verify slip or cancel",
            ),
            replace=True,
        )
        return

    record = ledger(context).insert_settled(draft.to_record())
    session.clear()
    sessions(context).save()
    await send_card(
        update,
        context,
        cards().success_card(record),
        replace=True,
    )


# --- command handlers ------------------------------------------------------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    sessions(context).get(update.effective_chat.id).clear()
    sessions(context).save()
    await show_dashboard(update, context)


async def cmd_ledger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    ledger_id = " ".join(context.args) if context.args else ""
    if not ledger_id:
        recent = ledger(context).recent(limit=5)
        if not recent:
            await send_card(
                update,
                context,
                cards().error_card(
                    "No records",
                    "Ledger is empty",
                    "Settle a transaction first",
                ),
                replace=False,
            )
            return
        lines = [cards().header(), cards().label("Recent Settlements"), ""]
        for item in recent:
            lines.append(
                f"{cards().mono(item.ledger_id)}  "
                f"{cards().mono(f'{item.thb:,.2f}')} THB  "
                f"{cards().mono(f'{item.usdt:.4f}')} USDT"
            )
        lines.extend(["", CardRenderer.SEP])
        await send_card(update, context, "\n".join(lines), replace=False)
        return

    record = ledger(context).get(ledger_id.upper())
    if not record:
        await send_card(
            update,
            context,
            cards().error_card(
                "Not found",
                f"No ledger entry for {ledger_id}",
                "Check Ledger ID and retry",
            ),
            replace=False,
        )
        return

    await send_card(
        update,
        context,
        cards().success_card(record),
        replace=False,
    )


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not context.args:
        await send_card(
            update,
            context,
            cards().error_card(
                "Missing Ledger ID",
                "No ID provided",
                "Use /delete LDG-YYYYMMDD-0001",
            ),
            replace=False,
        )
        return

    ledger_id = context.args[0].upper()
    record = ledger(context).get(ledger_id)
    if not record:
        await send_card(
            update,
            context,
            cards().error_card(
                "Not found",
                f"No ledger entry for {ledger_id}",
                "Verify Ledger ID",
            ),
            replace=False,
        )
        return

    session = sessions(context).get(update.effective_chat.id)
    session.mode = "delete"
    session.pending_delete_id = ledger_id
    sessions(context).save()
    await send_card(
        update,
        context,
        cards().delete_card(ledger_id),
        keyboard=delete_keyboard(),
        replace=False,
    )


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    await show_dashboard(update, context)


# --- message handlers ------------------------------------------------------


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update) or not update.effective_message or not update.message:
        return

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = bytes(await file.download_as_bytearray())

    session = sessions(context).get(update.effective_chat.id)
    if session.mode == "edit" and session.draft:
        await process_slip_flow(update, context, image_bytes, photo.file_id)
        return

    await process_slip_flow(update, context, image_bytes, photo.file_id)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update) or not update.effective_message or not update.message:
        return

    text = (update.message.text or "").strip()
    if text.startswith("/"):
        return

    usdt_match = USDT_PATTERN.match(text)
    if usdt_match:
        try:
            amount = Decimal(usdt_match.group(1))
        except InvalidOperation:
            amount = None
        if amount and amount > 0:
            await process_usdt_flow(update, context, amount)
            return

    if LEDGER_PATTERN.match(text.upper()):
        context.args = [text.upper()]
        await cmd_ledger(update, context)
        return

    await send_card(
        update,
        context,
        cards().error_card(
            "Unrecognized input",
            "Expected slip image or USDT amount",
            "Send slip  ·  12.5342  ·  /start",
        ),
        replace=False,
    )


# --- callback handlers -----------------------------------------------------


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update) or not update.callback_query:
        return

    query = update.callback_query
    await query.answer()
    data = query.data or ""
    session = sessions(context).get(update.effective_chat.id)

    if data == CB_CONFIRM:
        await settle_draft(update, context)
        return

    if data == CB_CANCEL:
        session.clear()
        sessions(context).save()
        await send_card(
            update,
            context,
            cards().error_card(
                "Cancelled",
                "Transaction discarded",
                "Send a new slip or USDT amount",
            ),
            replace=True,
        )
        return

    if data == CB_EDIT:
        if not session.draft:
            return
        session.mode = "edit"
        sessions(context).save()
        await send_card(
            update,
            context,
            cards().edit_card(session.draft),
            replace=True,
        )
        return

    if data == CB_HISTORY:
        draft = session.draft
        if not draft or not draft.bank or not draft.last4:
            return
        history = ledger(context).receiver_history(draft.bank, draft.last4)
        if not history:
            await send_card(
                update,
                context,
                cards().error_card(
                    "No history",
                    "Receiver not found in ledger",
                    "Continue with confirmation",
                ),
                replace=True,
            )
            return
        await send_card(
            update,
            context,
            cards().history_card(history),
            keyboard=confirm_keyboard(),
            replace=True,
        )
        return

    if data == CB_DELETE_CONFIRM:
        ledger_id = session.pending_delete_id
        if not ledger_id:
            return
        deleted = ledger(context).delete(ledger_id)
        session.clear()
        sessions(context).save()
        if deleted:
            await send_card(
                update,
                context,
                cards().error_card(
                    "Deleted",
                    f"Removed {ledger_id}",
                    "Entry removed from ledger",
                ),
                replace=True,
            )
        else:
            await send_card(
                update,
                context,
                cards().error_card(
                    "Delete failed",
                    f"Could not remove {ledger_id}",
                    "Retry or contact admin",
                ),
                replace=True,
            )
        return

    if data == CB_DELETE_CANCEL:
        session.mode = "idle"
        session.pending_delete_id = None
        sessions(context).save()
        await show_dashboard(update, context)


# --- app lifecycle ---------------------------------------------------------


async def on_shutdown(application: Application) -> None:
    sessions_store: SessionStore = application.bot_data["sessions"]
    sessions_store.save()


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN must be set")

    application = (
        Application.builder().token(token).post_shutdown(on_shutdown).build()
    )
    application.bot_data["rates"] = RateEngine()
    application.bot_data["ledger"] = LedgerStore()
    application.bot_data["sessions"] = SessionStore()

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_start))
    application.add_handler(CommandHandler("ledger", cmd_ledger))
    application.add_handler(CommandHandler("delete", cmd_delete))
    application.add_handler(CommandHandler("balance", cmd_balance))
    application.add_handler(CallbackQueryHandler(on_callback))
    application.add_handler(MessageHandler(filters.PHOTO, on_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    logger.info("CE VAULT starting")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
