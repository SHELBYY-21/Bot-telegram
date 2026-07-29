"""Async message helpers — prefer edit-in-place over new messages."""

from __future__ import annotations

from telegram import InlineKeyboardMarkup, Message
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes


async def show_typing(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)


async def send_card(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    *,
    keyboard: InlineKeyboardMarkup | None = None,
    reply_to: int | None = None,
) -> Message:
    return await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
        reply_to_message_id=reply_to,
        disable_web_page_preview=True,
    )


async def replace_card(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    chat_id: int,
    text: str,
    message_id: int | None,
    keyboard: InlineKeyboardMarkup | None = None,
) -> int:
    """Edit an existing console message when possible. Returns message_id."""
    if message_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
            return message_id
        except BadRequest as exc:
            if "not modified" in str(exc).lower():
                return message_id
    msg = await send_card(context, chat_id, text, keyboard=keyboard)
    return msg.message_id
