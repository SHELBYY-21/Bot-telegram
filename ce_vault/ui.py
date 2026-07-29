"""Inline keyboards and message lifecycle — edit in place, never spam."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes


def kb_confirm(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Confirm", callback_data=f"cf:{ledger_id}"),
                InlineKeyboardButton("Edit", callback_data=f"ed:{ledger_id}"),
                InlineKeyboardButton("Cancel", callback_data=f"cx:{ledger_id}"),
            ]
        ]
    )


def kb_delete(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Delete", callback_data=f"dd:{ledger_id}"),
                InlineKeyboardButton("Keep", callback_data=f"kp:{ledger_id}"),
            ]
        ]
    )


def kb_done() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Done", callback_data="done")]])


def kb_usdt_waiting(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Mark Settled", callback_data=f"st:{ledger_id}"),
                InlineKeyboardButton("Cancel", callback_data=f"cx:{ledger_id}"),
            ]
        ]
    )


async def show_typing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat:
        await context.bot.send_chat_action(chat.id, ChatAction.TYPING)


async def send_card(
    update: Update,
    text: str,
    *,
    keyboard: InlineKeyboardMarkup | None = None,
    edit_message: Message | None = None,
) -> Message:
    """Prefer editing the previous console message; fall back to a new reply."""
    if edit_message is not None:
        try:
            return await edit_message.edit_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
        except Exception:
            pass

    assert update.effective_message
    return await update.effective_message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )


async def edit_card(
    message: Message,
    text: str,
    *,
    keyboard: InlineKeyboardMarkup | None = None,
) -> Message:
    return await message.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
