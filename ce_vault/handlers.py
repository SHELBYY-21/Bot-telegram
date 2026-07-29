"""CE VAULT Telegram handlers — one card, one decision."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from ce_vault import cards
from ce_vault.design import (
    CONFIDENCE_WARN,
    STATUS_OCR,
    STATUS_RECEIVED,
    STATUS_SETTLED,
    STATUS_WAITING,
)
from ce_vault.keyboards import (
    confirm_keyboard,
    delete_keyboard,
    done_keyboard,
    home_keyboard,
    ocr_keyboard,
)
from ce_vault.ledger import Ledger, new_ledger_id
from ce_vault.messaging import edit_card_message, send_card, show_typing
from ce_vault.models import OCRResult, Transaction, utc_now
from ce_vault.ocr import run_ocr, slip_hash_from_bytes, slip_hash_from_file_id
from ce_vault.rates import current_rates, quote_from_thb, quote_from_usdt

logger = logging.getLogger("ce_vault.handlers")

USDT_RE = re.compile(
    r"^\s*(?:usdt\s*)?([0-9]+(?:\.[0-9]+)?)\s*(?:usdt)?\s*$",
    re.IGNORECASE,
)


def allowed_user_ids() -> set[int]:
    raw = os.environ.get("ALLOWED_USER_IDS", "").strip()
    return {int(x) for x in raw.replace(",", " ").split()} if raw else set()


def authorized(update: Update) -> bool:
    allowed = allowed_user_ids()
    if not allowed:
        return True
    return bool(update.effective_user) and update.effective_user.id in allowed


def ledger(context: ContextTypes.DEFAULT_TYPE) -> Ledger:
    return context.application.bot_data["ledger"]


def _staff(update: Update) -> tuple[int, str]:
    user = update.effective_user
    if not user:
        return 0, "system"
    return user.id, (user.username or user.full_name or str(user.id))


def _apply_quote(tx: Transaction, thb: float | None = None, usdt: float | None = None) -> Transaction:
    if thb is not None and thb > 0:
        q = quote_from_thb(thb)
    elif usdt is not None and usdt > 0:
        q = quote_from_usdt(usdt)
    else:
        raise ValueError("THB or USDT required")
    tx.thb = q.thb
    tx.usdt = q.usdt
    tx.buy_rate = q.buy_rate
    tx.sell_rate = q.sell_rate
    tx.profit_pct = q.profit_pct
    tx.profit_thb = q.profit_thb
    return tx


def _session(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    return context.user_data.setdefault("vault", {})


# --- Commands --------------------------------------------------------------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    await show_typing(update, context)
    db = ledger(context)
    text = cards.console_home(
        balance_usdt=db.get_balance(),
        open_count=db.open_count(),
        settled_today=db.settled_today_count(),
    )
    await send_card(update, context, text, keyboard=home_keyboard())


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    guide = (
        f"{cards.header(subtitle='Operator Guide')}\n\n"
        "<b>Intake</b>\nSlip image  ·  USDT amount\n\n"
        "<b>Pipeline</b>\nRECEIVED → OCR VERIFIED → WAITING USDT → SETTLED\n\n"
        "<b>Commands</b>\n"
        "<code>/console</code>  home\n"
        "<code>/rates</code>  live quote\n"
        "<code>/ledger &lt;id&gt;</code>  open card\n"
        "<code>/history &lt;bank&gt; &lt;last4&gt;</code>\n"
        "<code>/balance</code>  vault USDT"
    )
    await send_card(update, context, guide)


async def cmd_console(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def cmd_rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    buy, sell = current_rates()
    spread = ((sell - buy) / buy) * 100
    text = "\n".join(
        [
            cards.header(subtitle="Rate Desk"),
            "",
            f"<b>Buy Rate</b>\n<code>{buy:.2f}</code>",
            "",
            f"<b>Sell Rate</b>\n<code>{sell:.2f}</code>",
            "",
            f"<b>Spread</b>\n<code>+{spread:.2f}%</code>",
        ]
    )
    await send_card(update, context, text)


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    bal = ledger(context).get_balance()
    text = "\n".join(
        [
            cards.header(subtitle="Vault Balance"),
            "",
            f"<b>USDT</b>\n<code>{bal:,.4f}</code>",
        ]
    )
    await send_card(update, context, text)


async def cmd_ledger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not context.args:
        await send_card(
            update,
            context,
            cards.error_card("Missing Ledger ID", "No identifier supplied.", "Use /ledger <id>"),
        )
        return
    tx = ledger(context).get(context.args[0])
    if not tx:
        await send_card(
            update,
            context,
            cards.error_card("Not Found", "Ledger ID does not exist.", "Check the identifier and retry."),
        )
        return
    kb = confirm_keyboard(tx.ledger_id) if tx.status != STATUS_SETTLED else done_keyboard(tx.ledger_id)
    await send_card(update, context, cards.confirmation_card(tx), keyboard=kb)


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not context.args or len(context.args) < 2:
        await send_card(
            update,
            context,
            cards.error_card(
                "Missing Receiver",
                "Bank code and last4 required.",
                "Use /history SCB 3376",
            ),
        )
        return
    bank, last4 = context.args[0].upper(), context.args[1][-4:]
    hist = ledger(context).receiver_history(bank, last4)
    await send_card(update, context, cards.history_card(hist))


async def cmd_setbalance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not context.args:
        await send_card(
            update,
            context,
            cards.error_card("Missing Amount", "USDT balance required.", "Use /setbalance 10000"),
        )
        return
    try:
        value = float(context.args[0].replace(",", ""))
    except ValueError:
        await send_card(
            update,
            context,
            cards.error_card("Invalid Amount", "Could not parse USDT.", "Send a numeric value."),
        )
        return
    ledger(context).set_balance(value)
    await cmd_balance(update, context)


# --- Intake ----------------------------------------------------------------


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    assert update.effective_message and update.effective_chat
    photos = update.effective_message.photo
    if not photos:
        return

    await show_typing(update, context)
    staff_id, staff_name = _staff(update)
    db = ledger(context)
    ledger_id = new_ledger_id()

    msg = await send_card(
        update,
        context,
        cards.receive_card(ledger_id, progress="Ingesting slip…"),
    )

    photo = photos[-1]
    file_id = photo.file_id
    image_bytes: bytes | None = None
    try:
        tg_file = await context.bot.get_file(file_id)
        image_bytes = bytes(await tg_file.download_as_bytearray())
        slip_hash = slip_hash_from_bytes(image_bytes)
    except Exception as exc:
        logger.warning("download failed: %s", exc)
        slip_hash = slip_hash_from_file_id(file_id)

    dup = db.find_by_slip_hash(slip_hash)
    caption = update.effective_message.caption

    await edit_card_message(
        context,
        update.effective_chat.id,
        msg.message_id,
        cards.loading_card(ledger_id, label="Vision · scanning"),
    )

    ocr = await run_ocr(image_bytes, file_id, caption)
    if dup:
        ocr.duplicate = True
        ocr.warning = f"Duplicate of {dup.ledger_id}"

    warn = ocr.confidence < CONFIDENCE_WARN or ocr.duplicate

    tx = Transaction(
        ledger_id=ledger_id,
        status=STATUS_OCR,
        receiver_name=ocr.receiver_name,
        bank=ocr.bank,
        last4=ocr.last4,
        confidence=ocr.confidence,
        slip_hash=slip_hash,
        slip_ref=ocr.slip_ref,
        staff_id=staff_id,
        staff_name=staff_name,
        chat_id=update.effective_chat.id,
        message_id=msg.message_id,
        image_file_id=file_id,
        ocr_json=json.dumps(ocr.to_dict(), ensure_ascii=False),
    )
    if ocr.amount_thb > 0:
        _apply_quote(tx, thb=ocr.amount_thb)

    # Receiver frequency signal
    hist = db.receiver_history(tx.bank, tx.last4) if tx.bank and tx.last4 else None
    if hist and hist.tx_count >= 5 and not ocr.warning:
        ocr.warning = f"Repeated receiver · {hist.tx_count} prior"

    db.create(tx)
    session = _session(context)
    session["active_ledger"] = ledger_id
    session["message_id"] = msg.message_id
    session.pop("edit_ledger", None)

    await edit_card_message(
        context,
        update.effective_chat.id,
        msg.message_id,
        cards.ocr_card(ledger_id, ocr, warn=warn),
        keyboard=ocr_keyboard(ledger_id, warn=warn),
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    assert update.effective_message and update.effective_chat
    text = (update.effective_message.text or "").strip()
    if not text or text.startswith("/"):
        return

    session = _session(context)
    db = ledger(context)

    # Edit mode — staff sends corrected USDT
    edit_id = session.get("edit_ledger")
    if edit_id:
        m = USDT_RE.match(text)
        if not m:
            await send_card(
                update,
                context,
                cards.error_card(
                    "Invalid Input",
                    "Edit mode expects a USDT amount.",
                    "Send e.g. 12.5342",
                ),
                edit_message_id=session.get("message_id"),
            )
            return
        usdt = float(m.group(1))
        tx = db.get(edit_id)
        if not tx:
            session.pop("edit_ledger", None)
            await send_card(
                update,
                context,
                cards.error_card("Not Found", "Ledger vanished.", "Start a new intake."),
            )
            return
        _apply_quote(tx, usdt=usdt)
        tx.status = STATUS_WAITING
        db.update(tx)
        session.pop("edit_ledger", None)
        mid = tx.message_id or session.get("message_id")
        msg = await send_card(
            update,
            context,
            cards.confirmation_card(tx),
            keyboard=confirm_keyboard(tx.ledger_id),
            edit_message_id=mid,
        )
        tx.message_id = msg.message_id
        db.update(tx)
        session["message_id"] = msg.message_id
        session["active_ledger"] = tx.ledger_id
        return

    m = USDT_RE.match(text)
    if not m:
        await send_card(
            update,
            context,
            cards.error_card(
                "Unrecognized Input",
                "Console accepts slip images or USDT amounts only.",
                "Send a photo slip, or type e.g. 12.5",
            ),
        )
        return

    await show_typing(update, context)
    usdt = float(m.group(1))
    staff_id, staff_name = _staff(update)
    ledger_id = new_ledger_id()
    tx = Transaction(
        ledger_id=ledger_id,
        status=STATUS_WAITING,
        staff_id=staff_id,
        staff_name=staff_name,
        chat_id=update.effective_chat.id,
        confidence=100.0,
        receiver_name="Manual",
        bank="MANUAL",
        last4="0000",
    )
    _apply_quote(tx, usdt=usdt)
    msg = await send_card(
        update,
        context,
        cards.confirmation_card(tx),
        keyboard=confirm_keyboard(ledger_id),
    )
    tx.message_id = msg.message_id
    db.create(tx)
    session["active_ledger"] = ledger_id
    session["message_id"] = msg.message_id


# --- Callbacks -------------------------------------------------------------


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    data = query.data
    db = ledger(context)
    session = _session(context)
    chat_id = update.effective_chat.id if update.effective_chat else 0
    message_id = query.message.message_id if query.message else None

    if data == "new":
        await cmd_start(update, context)
        return

    if data == "rates":
        await cmd_rates(update, context)
        return

    if data == "open":
        rows = [t for t in db.recent(20) if t.status != STATUS_SETTLED]
        if not rows:
            text = cards.error_card(
                "No Open Ledgers",
                "Vault has no pending entries.",
                "Send a slip to open a ledger.",
            )
        else:
            lines = [cards.header(subtitle="Open Ledgers"), ""]
            for t in rows[:8]:
                lines.append(
                    f"<code>{t.ledger_id}</code>  {_status_short(t.status)}  "
                    f"<code>{t.thb:,.2f}</code> THB"
                )
                lines.append("")
            text = "\n".join(lines).rstrip()
        await send_card(update, context, text, edit_message_id=message_id)
        return

    if ":" not in data:
        return
    action, ledger_id = data.split(":", 1)
    tx = db.get(ledger_id)

    if action == "ocr_ok":
        if not tx:
            return
        if tx.thb <= 0:
            session["edit_ledger"] = ledger_id
            session["message_id"] = message_id
            text = cards.edit_card(tx, hint="Amount missing — send USDT amount")
            await edit_card_message(context, chat_id, message_id, text)
            return
        tx.status = STATUS_WAITING
        db.update(tx)
        await edit_card_message(
            context,
            chat_id,
            message_id,
            cards.confirmation_card(tx),
            keyboard=confirm_keyboard(ledger_id),
        )
        return

    if action == "edit":
        if not tx:
            return
        session["edit_ledger"] = ledger_id
        session["message_id"] = message_id
        await edit_card_message(
            context,
            chat_id,
            message_id,
            cards.edit_card(tx),
        )
        return

    if action == "cancel":
        if tx:
            text = cards.delete_card(ledger_id, tx.receiver_mask())
            await edit_card_message(
                context,
                chat_id,
                message_id,
                text,
                keyboard=delete_keyboard(ledger_id),
            )
        return

    if action == "void":
        if tx:
            db.delete(ledger_id)
        session.pop("edit_ledger", None)
        session.pop("active_ledger", None)
        text = cards.error_card(
            "Ledger Voided",
            f"{ledger_id} removed from vault.",
            "Send a new slip to continue.",
        )
        await edit_card_message(context, chat_id, message_id, text)
        return

    if action == "keep":
        if not tx:
            return
        await edit_card_message(
            context,
            chat_id,
            message_id,
            cards.confirmation_card(tx),
            keyboard=confirm_keyboard(ledger_id),
        )
        return

    if action == "confirm":
        if not tx:
            return
        if tx.status == STATUS_SETTLED:
            await edit_card_message(
                context,
                chat_id,
                message_id,
                cards.success_card(
                    tx.ledger_id,
                    tx.profit_pct,
                    db.get_balance(),
                    tx.profit_thb,
                ),
                keyboard=done_keyboard(ledger_id),
            )
            return
        tx.status = STATUS_SETTLED
        tx.settled_at = utc_now()
        db.update(tx)
        # Paying out USDT reduces vault balance
        new_bal = db.adjust_balance(-tx.usdt)
        await edit_card_message(
            context,
            chat_id,
            message_id,
            cards.success_card(tx.ledger_id, tx.profit_pct, new_bal, tx.profit_thb),
            keyboard=done_keyboard(ledger_id),
        )
        session.pop("edit_ledger", None)
        return

    if action == "history":
        if not tx or not tx.last4:
            return
        hist = db.receiver_history(tx.bank, tx.last4)
        await send_card(update, context, cards.history_card(hist))
        return


def _status_short(status: str) -> str:
    return {
        STATUS_RECEIVED: "RECV",
        STATUS_OCR: "OCR",
        STATUS_WAITING: "WAIT",
        STATUS_SETTLED: "DONE",
    }.get(status, status[:4])
