"""Messaging primitives — edit-in-place, typing, single-card replies."""

from __future__ import annotations

import logging
from typing import Any

from telegram import InlineKeyboardMarkup, Message, Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

logger = logging.getLogger("ce_vault.messaging")


async def show_typing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if not chat:
        return
    try:
        await context.bot.send_chat_action(chat.id, ChatAction.TYPING)
    except Exception:
        pass


async def send_card(
    update: Update,
    text: str,
    *,
    keyboard: InlineKeyboardMarkup | None = None,
    edit_message: Message | None = None,
) -> Message:
    """Send or edit a single card. Prefer editing when possible."""
    assert update.effective_message
    kwargs: dict[str, Any] = {
        "text": text,
        "parse_mode": ParseMode.HTML,
        "disable_web_page_preview": True,
        "reply_markup": keyboard,
    }
    target = edit_message
    if target is None:
        # Reuse tracked message from chat_data if present
        pass

    if target is not None:
        try:
            return await target.edit_text(**kwargs)
        except BadRequest as e:
            if "message is not modified" in str(e).lower():
                return target
            logger.debug("edit failed, sending new: %s", e)

    return await update.effective_message.reply_text(**kwargs)


async def edit_or_send(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    *,
    message_id: int | None = None,
    keyboard: InlineKeyboardMarkup | None = None,
) -> Message:
    kwargs: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": ParseMode.HTML,
        "disable_web_page_preview": True,
        "reply_markup": keyboard,
    }
    if message_id is not None:
        try:
            return await context.bot.edit_message_text(message_id=message_id, **kwargs)
        except BadRequest as e:
            if "message is not modified" in str(e).lower():
                # fabricate a minimal stand-in isn't possible; re-send
                pass
            else:
                logger.debug("edit_message_text failed: %s", e)
    return await context.bot.send_message(**kwargs)


def track_console_message(context: ContextTypes.DEFAULT_TYPE, message: Message) -> None:
    context.chat_data["console_message_id"] = message.message_id


def tracked_message_id(context: ContextTypes.DEFAULT_TYPE) -> int | None:
    return context.chat_data.get("console_message_id")
