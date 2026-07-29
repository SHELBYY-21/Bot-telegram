"""Text message handlers for USDT amounts."""

from __future__ import annotations

import logging
import re

from telegram import Update
from telegram.ext import ContextTypes

from bot.auth import authorized
from bot.keyboards import confirm_keyboard
from bot.messaging import send_card, typing
from cards.confirmation import confirmation_card
from cards.error import error_card
from cards.receive import receive_card
from services.ledger import LedgerService

logger = logging.getLogger(__name__)

USDT_PATTERN = re.compile(r"^[\s]*([0-9]+(?:\.[0-9]{1,4})?)[\s]*(?:usdt)?[\s]*$", re.IGNORECASE)


def _ledger(context: ContextTypes.DEFAULT_TYPE) -> LedgerService:
    return context.application.bot_data["ledger"]


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return

    assert update.effective_message and update.effective_user
    text = (update.effective_message.text or "").strip()
    if text.startswith("/"):
        return

    staff_id = update.effective_user.id
    ledger = _ledger(context)

    m = USDT_PATTERN.match(text)
    if not m:
        await send_card(
            update, context,
            error_card(
                "Unrecognized Input",
                "Expected USDT amount or slip photo",
                "Send a number like 12.5342 or a slip image",
            ),
        )
        return

    usdt = float(m.group(1))
    if usdt <= 0:
        await send_card(
            update, context,
            error_card("Invalid Amount", "USDT must be positive", "Enter a valid amount"),
        )
        return

    await typing(update, context)

    editing = context.chat_data.get("editing")
    if editing:
        tx = ledger.apply_usdt(editing, usdt)
        context.chat_data.pop("editing", None)
        if not tx:
            await send_card(update, context, error_card("Failed", "Could not update", "Try again"))
            return
        await send_card(
            update, context,
            confirmation_card(tx),
            keyboard=confirm_keyboard(editing),
            edit=True,
        )
        return

    pending = ledger.repo.get_pending_for_staff(staff_id)
    if pending and pending.get("ocr_data"):
        tx = ledger.apply_usdt(pending["id"], usdt)
        if tx:
            await send_card(
                update, context,
                confirmation_card(tx),
                keyboard=confirm_keyboard(pending["id"]),
                edit=True,
            )
            return

    tx = ledger.start_from_usdt(staff_id, usdt)
    context.chat_data["pending_ledger"] = tx["id"]
    await send_card(update, context, receive_card(tx))
    from cards.base import header, SEP
    wait_text = "\n".join([
        header(tx["id"]),
        "",
        "USDT",
        f"<code>{usdt:,.4f}</code>",
        "",
        "Send slip photo to continue",
        SEP,
    ])
    await send_card(update, context, wait_text, edit=True)
