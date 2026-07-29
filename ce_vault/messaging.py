"""Message UX — edit-in-place, typing, single-card delivery."""

from __future__ import annotations

import logging

from telegram import InlineKeyboardMarkup, Message, Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

logger = logging.getLogger("ce_vault.messaging")


async def show_typing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if not chat:
        return
    await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)


async def send_card(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    keyboard: InlineKeyboardMarkup | None = None,
    edit_message_id: int | None = None,
) -> Message:
    """Prefer editing the previous console message; fall back to a new send."""
    assert update.effective_chat
    chat_id = update.effective_chat.id
    kwargs = {"parse_mode": ParseMode.HTML, "disable_web_page_preview": True}

    if edit_message_id is not None:
        try:
            return await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=edit_message_id,
                text=text,
                reply_markup=keyboard,
                **kwargs,
            )
        except BadRequest as exc:
            if "not modified" in str(exc).lower():
                msg = update.effective_message
                assert msg
                return msg
            logger.debug("edit failed (%s), sending new card", exc)

    assert update.effective_message
    return await update.effective_message.reply_text(
        text, reply_markup=keyboard, **kwargs
    )


async def edit_card_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
    text: str,
    keyboard: InlineKeyboardMarkup | None = None,
) -> None:
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            logger.warning("card edit failed: %s", exc)
