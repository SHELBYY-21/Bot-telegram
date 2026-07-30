"""Message console — edit-in-place, never spam."""

from __future__ import annotations

import logging
from typing import Any

from telegram import InlineKeyboardMarkup, Message, Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

logger = logging.getLogger("ce_vault.console")


async def show_typing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat:
        await context.bot.send_chat_action(chat.id, ChatAction.TYPING)


async def render(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    keyboard: InlineKeyboardMarkup | None = None,
    edit_message_id: int | None = None,
    prefer_edit: bool = True,
) -> Message:
    """Render a single card. Prefer editing the active console message."""
    chat = update.effective_chat
    assert chat is not None

    kwargs: dict[str, Any] = {
        "parse_mode": ParseMode.HTML,
        "disable_web_page_preview": True,
        "reply_markup": keyboard,
    }

    message_id = edit_message_id
    if message_id is None and prefer_edit:
        sess = context.application.bot_data["sessions"].get(chat.id)
        message_id = sess.console_message_id

    if message_id and prefer_edit:
        try:
            msg = await context.bot.edit_message_text(
                chat_id=chat.id,
                message_id=message_id,
                text=text,
                **kwargs,
            )
            context.application.bot_data["sessions"].update(
                chat.id, console_message_id=msg.message_id
            )
            return msg
        except BadRequest as exc:
            # Message not modified / too old / missing — fall through to send
            if "message is not modified" in str(exc).lower():
                # Still a success from UX perspective
                if update.effective_message:
                    return update.effective_message
            logger.debug("edit failed, sending new card: %s", exc)

    # Callback queries without a message to reply to
    if update.callback_query and update.callback_query.message:
        try:
            msg = await update.callback_query.message.edit_text(text, **kwargs)
            context.application.bot_data["sessions"].update(
                chat.id, console_message_id=msg.message_id
            )
            return msg
        except BadRequest as exc:
            if "message is not modified" in str(exc).lower():
                return update.callback_query.message
            logger.debug("callback edit failed: %s", exc)

    assert update.effective_message is not None or chat is not None
    if update.effective_message and not update.callback_query:
        msg = await update.effective_message.reply_text(text, **kwargs)
    else:
        msg = await context.bot.send_message(chat.id, text, **kwargs)

    context.application.bot_data["sessions"].update(
        chat.id, console_message_id=msg.message_id
    )
    return msg


async def answer_callback(update: Update, text: str | None = None) -> None:
    if update.callback_query:
        await update.callback_query.answer(text=text)
