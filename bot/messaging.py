"""Message send/edit helpers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram import InlineKeyboardMarkup, Message, Update
from telegram.constants import ChatAction, ParseMode

if TYPE_CHECKING:
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def send_card(
    update: Update,
    context: "ContextTypes.DEFAULT_TYPE",
    text: str,
    keyboard: InlineKeyboardMarkup | None = None,
    *,
    edit: bool = False,
) -> Message | None:
    """Send or edit a single card message."""
    kwargs = {
        "text": text,
        "parse_mode": ParseMode.HTML,
        "disable_web_page_preview": True,
    }
    if keyboard:
        kwargs["reply_markup"] = keyboard

    chat_data = context.chat_data

    if edit and chat_data.get("last_card_id"):
        try:
            msg = await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=chat_data["last_card_id"],
                **kwargs,
            )
            return msg
        except Exception as e:
            logger.debug("Edit failed, sending new: %s", e)

    assert update.effective_message or update.effective_chat
    if update.callback_query and update.callback_query.message:
        try:
            msg = await update.callback_query.message.edit_text(**kwargs)
            chat_data["last_card_id"] = msg.message_id
            return msg
        except Exception:
            pass

    target = update.effective_message or update.effective_chat
    msg = await target.reply_text(**kwargs)
    chat_data["last_card_id"] = msg.message_id
    return msg


async def typing(update: Update, context: "ContextTypes.DEFAULT_TYPE") -> None:
    if update.effective_chat:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
