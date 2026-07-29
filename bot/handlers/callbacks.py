"""Callback query handlers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.auth import authorized
from bot.keyboards import confirm_keyboard, done_keyboard, edit_keyboard
from bot.messaging import send_card
from cards.confirmation import confirmation_card
from cards.error import error_card
from cards.history import history_card
from cards.success import success_card
from services.ledger import LedgerService

logger = logging.getLogger(__name__)


def _ledger(context: ContextTypes.DEFAULT_TYPE) -> LedgerService:
    return context.application.bot_data["ledger"]


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return

    query = update.callback_query
    assert query and query.data
    await query.answer()

    data = query.data
    ledger = _ledger(context)

    if data == "new_tx":
        context.chat_data.pop("pending_ledger", None)
        context.chat_data.pop("editing", None)
        from bot.handlers.commands import HELP
        await send_card(update, context, HELP, edit=True)
        return

    if ":" not in data:
        return

    action, ledger_id = data.split(":", 1)
    tx = ledger.repo.get_transaction(ledger_id)

    if action == "confirm":
        if not tx:
            await send_card(update, context, error_card("Not Found", "Transaction missing", "Start over"), edit=True)
            return
        if not tx.get("thb") or not tx.get("usdt"):
            await send_card(
                update, context,
                error_card("Incomplete", "Missing THB or USDT", "Send USDT amount or slip"),
                edit=True,
            )
            return
        settled = ledger.settle(ledger_id)
        if not settled:
            await send_card(update, context, error_card("Failed", "Could not settle", "Try again"), edit=True)
            return
        context.chat_data.pop("pending_ledger", None)
        await send_card(update, context, success_card(settled), keyboard=done_keyboard(), edit=True)
        return

    if action == "cancel":
        ledger.cancel(ledger_id)
        context.chat_data.pop("pending_ledger", None)
        context.chat_data.pop("editing", None)
        await send_card(
            update, context,
            error_card("Cancelled", f"Transaction {ledger_id} cancelled", "Send a new slip"),
            edit=True,
        )
        return

    if action == "edit":
        context.chat_data["editing"] = ledger_id
        await send_card(
            update, context,
            confirmation_card(tx) if tx else error_card("Not Found", "Transaction missing", "Start over"),
            keyboard=edit_keyboard(ledger_id),
            edit=True,
        )
        return

    if action == "edit_usdt":
        context.chat_data["editing"] = ledger_id
        from cards.base import header, SEP
        text = "\n".join([
            header(ledger_id),
            "",
            "Send USDT amount",
            SEP,
        ])
        await send_card(update, context, text, edit=True)
        return

    if action == "back":
        context.chat_data.pop("editing", None)
        if tx:
            await send_card(
                update, context,
                confirmation_card(tx),
                keyboard=confirm_keyboard(ledger_id),
                edit=True,
            )
        return

    if action == "history":
        receiver_id = int(ledger_id)
        receiver = ledger.repo.get_receiver(receiver_id)
        if receiver:
            risk = ledger.assess_risk(receiver)
            await send_card(update, context, history_card(receiver, risk), edit=True)
