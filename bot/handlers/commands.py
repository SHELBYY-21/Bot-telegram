"""Command handlers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import ContextTypes

from bot.auth import authorized
from bot.messaging import send_card
from cards.confirmation import confirmation_card
from cards.error import error_card
from cards.history import history_card
from db.repository import Repository
from services.ledger import LedgerService
from services.rates import get_rates

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

HELP = (
    "<b>CE VAULT</b>\n"
    "<i>Secure Ledger</i>\n"
    "────────────────\n\n"
    "Send a <b>bank slip photo</b> to receive.\n"
    "Or send a <b>USDT amount</b> to start.\n\n"
    "/balance — current USDT balance\n"
    "/rates — active exchange rates\n"
    "/history — recent transactions\n"
    "/ledger &lt;id&gt; — view transaction\n"
    "/cancel — cancel pending transaction"
)


def _repo(context: ContextTypes.DEFAULT_TYPE) -> Repository:
    return context.application.bot_data["repo"]


def _ledger(context: ContextTypes.DEFAULT_TYPE) -> LedgerService:
    return context.application.bot_data["ledger"]


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    await send_card(update, context, HELP)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    repo = _repo(context)
    staff_id = update.effective_user.id
    balance = repo.get_balance(staff_id)
    from cards.base import header, money, SEP
    text = "\n".join([
        header(),
        "",
        "USDT Balance",
        money(balance, "USDT"),
        SEP,
    ])
    await send_card(update, context, text)


async def cmd_rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    rates = get_rates(_repo(context))
    from cards.base import header, money, pct, SEP
    text = "\n".join([
        header(),
        "",
        "Buy Rate",
        money(rates.buy_rate),
        "",
        "Sell Rate",
        money(rates.sell_rate),
        "",
        "Spread",
        pct(rates.profit_pct()),
        SEP,
    ])
    await send_card(update, context, text)


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    repo = _repo(context)
    staff_id = update.effective_user.id
    txs = repo.list_transactions(staff_id=staff_id, limit=10)
    if not txs:
        await send_card(
            update, context,
            error_card("No History", "No transactions recorded", "Send a slip to begin"),
        )
        return

    from cards.base import header, money, esc, SEP
    lines = [header(), "", "Recent Transactions", ""]
    for tx in txs[:5]:
        lines.append(f"{esc(tx['id'])}  {esc(tx['status'])}")
        if tx.get("thb"):
            lines.append(f"  {money(tx['thb'], 'THB')}  →  {money(tx.get('usdt'), 'USDT')}")
        lines.append("")
    lines.append(SEP)
    await send_card(update, context, "\n".join(lines))


async def cmd_ledger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not context.args:
        await send_card(
            update, context,
            error_card("Missing ID", "No ledger ID provided", "Use /ledger LV-YYYYMMDD-XXXX"),
        )
        return
    ledger_id = context.args[0]
    tx = _repo(context).get_transaction(ledger_id)
    if not tx:
        await send_card(
            update, context,
            error_card("Not Found", f"No transaction {ledger_id}", "Check the ledger ID"),
        )
        return
    from bot.keyboards import confirm_keyboard
    keyboard = None
    if tx["status"] not in ("SETTLED", "CANCELLED"):
        keyboard = confirm_keyboard(ledger_id)
    await send_card(update, context, confirmation_card(tx), keyboard=keyboard)


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    repo = _repo(context)
    staff_id = update.effective_user.id
    pending = repo.get_pending_for_staff(staff_id)
    if not pending:
        await send_card(
            update, context,
            error_card("Nothing Pending", "No active transaction", "Send a slip or USDT amount"),
        )
        return
    _ledger(context).cancel(pending["id"])
    context.chat_data.pop("editing", None)
    await send_card(
        update, context,
        error_card("Cancelled", f"Transaction {pending['id']} cancelled", "Send a new slip to start"),
    )
