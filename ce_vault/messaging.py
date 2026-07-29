"""Message surface — edit-in-place, typing indicators, never spam."""

from __future__ import annotations

from telegram import InlineKeyboardMarkup, Message, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes
from telegram.error import BadRequest


async def show_typing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if not chat:
        return
    await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)


async def send_or_edit_card(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    keyboard: InlineKeyboardMarkup | None = None,
    message_id: int | None = None,
) -> Message:
    """Prefer editing the active console message; fall back to a single new card."""
    chat = update.effective_chat
    assert chat

    track = context.chat_data.setdefault("console", {})
    target_id = message_id or track.get("message_id")

    if target_id:
        try:
            msg = await context.bot.edit_message_text(
                chat_id=chat.id,
                message_id=target_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
            track["message_id"] = msg.message_id
            return msg
        except BadRequest as exc:
            # "message is not modified" is fine — keep the same card.
            if "not modified" in str(exc).lower():
                # Fabricate minimal access via existing id
                if update.effective_message and update.effective_message.message_id == target_id:
                    return update.effective_message
            # Otherwise fall through to send a fresh card.

    # Callback queries often have no message text we own — reply on the chat.
    if update.callback_query and update.callback_query.message:
        try:
            msg = await update.callback_query.message.edit_text(
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
            track["message_id"] = msg.message_id
            return msg
        except BadRequest:
            pass

    assert update.effective_message
    msg = await context.bot.send_message(
        chat_id=chat.id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
    track["message_id"] = msg.message_id
    return msg


def remember_ledger(context: ContextTypes.DEFAULT_TYPE, ledger_id: str) -> None:
    context.chat_data.setdefault("console", {})["ledger_id"] = ledger_id


def active_ledger_id(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    return context.chat_data.get("console", {}).get("ledger_id")


def set_edit_mode(context: ContextTypes.DEFAULT_TYPE, mode: str | None) -> None:
    console = context.chat_data.setdefault("console", {})
    if mode is None:
        console.pop("edit_mode", None)
    else:
        console["edit_mode"] = mode


def get_edit_mode(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    return context.chat_data.get("console", {}).get("edit_mode")
