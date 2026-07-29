"""Console messaging — edit-in-place, never spam."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes


def tx_keyboard(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Confirm", callback_data=f"tx:confirm:{ledger_id}"),
                InlineKeyboardButton("Edit", callback_data=f"tx:edit:{ledger_id}"),
                InlineKeyboardButton("Cancel", callback_data=f"tx:cancel:{ledger_id}"),
            ]
        ]
    )


def edit_keyboard(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Back", callback_data=f"tx:back:{ledger_id}"),
                InlineKeyboardButton("Cancel", callback_data=f"tx:cancel:{ledger_id}"),
            ]
        ]
    )


def delete_keyboard(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Delete", callback_data=f"tx:delete:{ledger_id}"),
                InlineKeyboardButton("Keep", callback_data=f"tx:back:{ledger_id}"),
            ]
        ]
    )


def settle_keyboard(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Mark Settled", callback_data=f"tx:settle:{ledger_id}"),
                InlineKeyboardButton("Cancel", callback_data=f"tx:cancel:{ledger_id}"),
            ]
        ]
    )


async def send_card(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    keyboard: InlineKeyboardMarkup | None = None,
    edit_message_id: int | None = None,
) -> Message:
    """Send or edit a single card. Prefers editing the previous console message."""
    chat = update.effective_chat
    assert chat

    # Prefer explicit edit target, then session message, then callback message.
    session = context.chat_data.get("console") or {}
    target_id = edit_message_id or session.get("message_id")

    if update.callback_query and update.callback_query.message and not edit_message_id:
        target_id = update.callback_query.message.message_id

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
            context.chat_data["console"] = {"message_id": msg.message_id}
            return msg
        except BadRequest as e:
            # Message is identical or not editable — fall through to send.
            if "message is not modified" in str(e).lower():
                msg = update.callback_query.message if update.callback_query else None
                if msg:
                    return msg

    assert update.effective_message
    msg = await context.bot.send_message(
        chat_id=chat.id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
    context.chat_data["console"] = {"message_id": msg.message_id}
    return msg


async def typing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)


def remember_ledger(context: ContextTypes.DEFAULT_TYPE, ledger_id: str) -> None:
    context.chat_data["active_ledger"] = ledger_id


def active_ledger(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    return context.chat_data.get("active_ledger")


def set_edit_mode(context: ContextTypes.DEFAULT_TYPE, ledger_id: str | None) -> None:
    if ledger_id:
        context.chat_data["edit_ledger"] = ledger_id
    else:
        context.chat_data.pop("edit_ledger", None)


def edit_mode(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    return context.chat_data.get("edit_ledger")
