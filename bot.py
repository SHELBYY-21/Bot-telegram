"""CE VAULT — Premium FinTech Operations Console for Telegram.

Send a payment slip image or a USDT amount. Rates, profit, and ledger
entries are calculated automatically. One card per screen; messages are
edited in place whenever possible.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

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

from config import Settings, load_settings
from db.ledger import LedgerStore, new_ledger_id
from services.ocr import OCRService
from services.rates import RateService
from services.transaction import TransactionService
from ui.cards import (
    console_home,
    delete_card,
    edit_card,
    error_card,
    history_card,
    loading_card,
    ocr_card,
    receive_card,
    success_card,
    transaction_card,
)
from ui.session import ChatSession, SessionStore

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO
)
logger = logging.getLogger("vault")

USDT_PATTERN = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*(?:usdt)\s*$", re.IGNORECASE
)
THB_PATTERN = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*(?:thb|฿|baht)?\s*$", re.IGNORECASE
)
USDT_DECIMAL_PATTERN = re.compile(r"^\s*(\d+\.\d{3,8})\s*$")


def parse_amount(text: str) -> tuple[str, float] | None:
    """Return ('usdt'|'thb', value) or None."""
    if USDT_PATTERN.match(text):
        return "usdt", float(USDT_PATTERN.match(text).group(1))  # type: ignore[union-attr]
    if THB_PATTERN.match(text) and re.search(r"(thb|฿|baht)", text, re.I):
        return "thb", float(THB_PATTERN.match(text).group(1))  # type: ignore[union-attr]
    if USDT_DECIMAL_PATTERN.match(text):
        return "usdt", float(USDT_DECIMAL_PATTERN.match(text).group(1))  # type: ignore[union-attr]
    if THB_PATTERN.match(text):
        return "thb", float(THB_PATTERN.match(text).group(1))  # type: ignore[union-attr]
    return None

CB_CONFIRM = "vault:confirm"
CB_EDIT = "vault:edit"
CB_CANCEL = "vault:cancel"
CB_DELETE_YES = "vault:delete:yes"
CB_DELETE_NO = "vault:delete:no"


# --- auth ----------------------------------------------------------------

def authorized(update: Update, settings: Settings) -> bool:
    if not settings.allowed_user_ids:
        return True
    return bool(update.effective_user) and update.effective_user.id in settings.allowed_user_ids


# --- services ------------------------------------------------------------

def store(context: ContextTypes.DEFAULT_TYPE) -> LedgerStore:
    return context.application.bot_data["store"]


def sessions(context: ContextTypes.DEFAULT_TYPE) -> SessionStore:
    return context.application.bot_data["sessions"]


def tx_service(context: ContextTypes.DEFAULT_TYPE) -> TransactionService:
    return context.application.bot_data["tx"]


def settings(context: ContextTypes.DEFAULT_TYPE) -> Settings:
    return context.application.bot_data["settings"]


def images_dir(context: ContextTypes.DEFAULT_TYPE) -> Path:
    return context.application.bot_data["images_dir"]


# --- message helpers -----------------------------------------------------

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
                InlineKeyboardButton("Delete", callback_data=CB_DELETE_YES),
                InlineKeyboardButton("Keep", callback_data=CB_DELETE_NO),
            ]
        ]
    )


async def send_card(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    keyboard: InlineKeyboardMarkup | None = None,
    force_new: bool = False,
) -> int:
    assert update.effective_chat
    chat_id = update.effective_chat.id
    session = sessions(context).get(chat_id)

    if not force_new and session.message_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=session.message_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
            return session.message_id
        except Exception:
            logger.debug("edit failed, sending new message", exc_info=True)

    assert update.effective_message
    msg = await update.effective_message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
    session.message_id = msg.message_id
    sessions(context).set(chat_id, session)
    return msg.message_id


async def typing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)


# --- handlers ------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, settings(context)):
        return
    chat_id = update.effective_chat.id
    sessions(context).set(chat_id, ChatSession())
    await send_card(update, context, console_home(), force_new=True)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, settings(context)):
        return
    assert update.effective_message and update.effective_message.photo
    chat_id = update.effective_chat.id
    session = sessions(context).get(chat_id)

    ledger_id = session.ledger_id or new_ledger_id()
    session.ledger_id = ledger_id
    sessions(context).set(chat_id, session)

    await typing(update, context)
    await send_card(update, context, receive_card(ledger_id), force_new=not session.message_id)
    await asyncio.sleep(0.4)
    await send_card(update, context, loading_card(ledger_id, "Vision scan"))

    photo = update.effective_message.photo[-1]
    file = await photo.get_file()
    image_bytes = bytes(await file.download_as_bytearray())
    ocr_svc: OCRService = context.application.bot_data["ocr"]
    hint = update.effective_message.caption
    slip_hash = OCRService.hash_image(image_bytes)

    duplicate = tx_service(context).check_duplicate(slip_hash)
    if duplicate:
        await send_card(
            update,
            context,
            error_card(
                ledger_id=ledger_id,
                problem="Duplicate slip",
                cause=f"Already recorded as {duplicate}",
                action="Send a different slip or contact support",
            ),
            force_new=True,
        )
        sessions(context).clear(chat_id)
        return

    try:
        ocr_result = await ocr_svc.process(image_bytes, hint=hint)
    except Exception as exc:
        logger.exception("OCR failed")
        await send_card(
            update,
            context,
            error_card(
                ledger_id=ledger_id,
                problem="OCR failed",
                cause=str(exc),
                action="Retry with a clearer slip image",
            ),
            force_new=True,
        )
        sessions(context).clear(chat_id)
        return

    warn = ocr_result.confidence < settings(context).low_confidence_threshold
    await send_card(update, context, ocr_card(ledger_id, ocr_result, warn=warn))
    await asyncio.sleep(0.5)

    if not ocr_result.amount_thb:
        await send_card(
            update,
            context,
            error_card(
                ledger_id=ledger_id,
                problem="Amount not detected",
                cause="OCR could not read transfer amount",
                action="Send a clearer slip or enter USDT amount",
            ),
            force_new=True,
        )
        sessions(context).clear(chat_id)
        return

    image_path = ocr_svc.save_image(image_bytes, ledger_id, images_dir(context))
    pending = tx_service(context).create_from_ocr(
        ocr_result,
        slip_hash=slip_hash,
        image_path=image_path,
        status="OCR_VERIFIED",
    )
    session.ledger_id = pending.ledger_id
    session.mode = "confirm"
    session.card = "transaction"
    sessions(context).set(chat_id, session)

    text = transaction_card(pending, active_status="WAITING_USDT")
    await send_card(update, context, text, keyboard=confirm_keyboard())


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, settings(context)):
        return
    assert update.effective_message and update.effective_message.text
    text = update.effective_message.text.strip()
    chat_id = update.effective_chat.id
    session = sessions(context).get(chat_id)

    if session.mode == "edit" and session.ledger_id:
        await _apply_edit(update, context, text, session)
        return

    parsed = parse_amount(text)
    if not parsed:
        if text.startswith("/"):
            return
        await send_card(
            update,
            context,
            error_card(
                problem="Invalid input",
                cause="Expected USDT amount or slip image",
                action="Send e.g. 12.5342 or 500 thb",
            ),
            force_new=True,
        )
        return

    await typing(update, context)
    kind, amount = parsed
    if kind == "usdt":
        pending = tx_service(context).create_from_usdt(amount)
    else:
        pending = tx_service(context).create_from_thb(amount)

    session.ledger_id = pending.ledger_id
    session.mode = "confirm"
    session.card = "transaction"
    sessions(context).set(chat_id, session)

    card_text = transaction_card(pending, active_status="WAITING_USDT")
    await send_card(update, context, card_text, keyboard=confirm_keyboard(), force_new=True)


async def _apply_edit(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    session: ChatSession,
) -> None:
    assert session.ledger_id
    parsed = parse_amount(text)
    if not parsed:
        await send_card(
            update,
            context,
            error_card(
                ledger_id=session.ledger_id,
                problem="Invalid amount",
                cause="Could not parse THB or USDT value",
                action="Send e.g. 500 or 12.5342",
            ),
        )
        return

    kind, amount = parsed
    if kind == "usdt":
        pending = tx_service(context).update_amount(session.ledger_id, usdt=amount)
    else:
        pending = tx_service(context).update_amount(session.ledger_id, thb=amount)

    session.mode = "confirm"
    sessions(context).set(update.effective_chat.id, session)
    card_text = transaction_card(pending, active_status="WAITING_USDT")
    await send_card(update, context, card_text, keyboard=confirm_keyboard())


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, settings(context)):
        return
    query = update.callback_query
    assert query and query.data
    await query.answer()

    chat_id = update.effective_chat.id
    session = sessions(context).get(chat_id)
    if not session.ledger_id:
        await query.edit_message_text(
            console_home(), parse_mode=ParseMode.HTML, disable_web_page_preview=True
        )
        return

    data = query.data
    if data == CB_CONFIRM:
        await _confirm(update, context, session)
    elif data == CB_EDIT:
        session.mode = "edit"
        sessions(context).set(chat_id, session)
        pending = tx_service(context).get_pending(session.ledger_id)
        await query.edit_message_text(
            edit_card(pending),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    elif data == CB_CANCEL:
        session.mode = "delete"
        sessions(context).set(chat_id, session)
        await query.edit_message_text(
            delete_card(session.ledger_id),
            parse_mode=ParseMode.HTML,
            reply_markup=delete_keyboard(),
            disable_web_page_preview=True,
        )
    elif data == CB_DELETE_YES:
        tx_service(context).cancel(session.ledger_id)
        sessions(context).clear(chat_id)
        await query.edit_message_text(
            console_home(), parse_mode=ParseMode.HTML, disable_web_page_preview=True
        )
    elif data == CB_DELETE_NO:
        session.mode = "confirm"
        sessions(context).set(chat_id, session)
        pending = tx_service(context).get_pending(session.ledger_id)
        await query.edit_message_text(
            transaction_card(pending, active_status="WAITING_USDT"),
            parse_mode=ParseMode.HTML,
            reply_markup=confirm_keyboard(),
            disable_web_page_preview=True,
        )


async def _confirm(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    session: ChatSession,
) -> None:
    assert update.callback_query and session.ledger_id
    entry = tx_service(context).confirm(session.ledger_id)
    balance = tx_service(context).balance()
    sessions(context).clear(update.effective_chat.id)
    await update.callback_query.edit_message_text(
        success_card(entry, balance),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, settings(context)):
        return
    balance = tx_service(context).balance()
    from ui.theme import divider, format_thb, format_usdt, header, mono

    text = "\n".join(
        [
            header(),
            "Balance",
            divider(),
            f"THB           {mono(format_thb(balance['total_thb']))}",
            f"USDT          {mono(format_usdt(balance['total_usdt']))}",
        ]
    )
    await send_card(update, context, text, force_new=True)


async def cmd_ledger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, settings(context)):
        return
    entries = store(context).recent_entries(limit=5)
    if not entries:
        await send_card(
            update,
            context,
            console_home(),
            force_new=True,
        )
        return

    from ui.theme import divider, esc, format_thb, format_usdt, header, mono

    lines = [header(), "Recent Ledger", divider(), ""]
    for entry in entries:
        receiver = entry.masked_receiver or "—"
        lines.append(f"{mono(entry.id)}  {esc(receiver)}")
        lines.append(
            f"  {mono(format_thb(entry.thb))} THB  ·  {mono(format_usdt(entry.usdt))} USDT  ·  {esc(entry.status)}"
        )
        lines.append("")
    await send_card(update, context, "\n".join(lines).rstrip(), force_new=True)


# --- app lifecycle -------------------------------------------------------

def main() -> None:
    cfg = load_settings()
    images = Path("data/images")
    images.mkdir(parents=True, exist_ok=True)

    application = Application.builder().token(cfg.telegram_token).build()
    application.bot_data["settings"] = cfg
    application.bot_data["store"] = LedgerStore(cfg.database_path)
    application.bot_data["sessions"] = SessionStore(cfg.state_file)
    application.bot_data["images_dir"] = images
    application.bot_data["ocr"] = OCRService(
        provider=cfg.ocr_provider,
        google_vision_api_key=cfg.google_vision_api_key,
        low_confidence_threshold=cfg.low_confidence_threshold,
    )
    rates = RateService(cfg.default_buy_rate, cfg.default_sell_rate)
    application.bot_data["tx"] = TransactionService(
        application.bot_data["store"],
        rates,
        application.bot_data["ocr"],
        cfg.staff_name,
    )

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_start))
    application.add_handler(CommandHandler("balance", cmd_balance))
    application.add_handler(CommandHandler("ledger", cmd_ledger))
    application.add_handler(CallbackQueryHandler(on_callback))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )

    logger.info("CE VAULT console starting")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
