"""CE VAULT — Premium FinTech Operations Console (Telegram).

Not a chatbot. One screen = one decision. Cards edit in place.

Inputs staff may provide:
  • payment slip photo
  • OR a USDT amount

Buy Rate is never requested — always calculated automatically.
"""

from __future__ import annotations

import logging
import os
import re

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ce_vault import cards, flow, keyboards, messaging, ocr
from ce_vault.config import allowed_user_ids, ledger_path, require_telegram_token
from ce_vault.ledger import Ledger
from ce_vault.rates import current_rates, quote_from_thb
from ce_vault.theme import TxStatus

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO
)
logger = logging.getLogger("ce_vault")

USDT_RE = re.compile(
    r"^(?:usdt\s*)?(\d+(?:\.\d+)?)\s*(?:usdt)?$",
    re.IGNORECASE,
)


# --- auth ----------------------------------------------------------------

def authorized(update: Update) -> bool:
    allowed = allowed_user_ids()
    if not allowed:
        return True
    return bool(update.effective_user) and update.effective_user.id in allowed


def ledger(context: ContextTypes.DEFAULT_TYPE) -> Ledger:
    return context.application.bot_data["ledger"]


# --- commands ------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    await messaging.show_typing(update, context)
    store = ledger(context)
    text = cards.console_home(
        balance_usdt=store.get_balance(),
        open_count=store.open_count(update.effective_chat.id if update.effective_chat else None),
        settled_today=store.settled_today_count(
            update.effective_chat.id if update.effective_chat else None
        ),
    )
    # Fresh home card — clear previous track so we don't mutate an old tx card
    context.chat_data["console"] = {}
    await messaging.send_or_edit_card(update, context, text, keyboard=keyboards.home_keyboard())


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    await cmd_start(update, context)


async def cmd_rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    import html as _html

    from ce_vault import PRODUCT, TAGLINE
    from ce_vault.theme import RULE

    buy, sell = current_rates()
    sample = quote_from_thb(1000)
    text = "\n".join(
        [
            f"<b>{PRODUCT}</b>",
            f"<i>{TAGLINE}</i>",
            RULE,
            f"<b>Buy Rate</b>\n<code>{_html.escape(f'{buy:,.2f}')}</code>",
            "",
            f"<b>Sell Rate</b>\n<code>{_html.escape(f'{sell:,.2f}')}</code>",
            "",
            f"<b>Profit</b>\n<code>{_html.escape(f'{sample.profit_pct:+.2f}%')}</code>",
            RULE,
            "<i>Rates apply automatically. Never enter Buy Rate.</i>",
        ]
    )
    await messaging.send_or_edit_card(update, context, text)


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    await cmd_start(update, context)


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not context.args or len(context.args) < 2:
        text = cards.error_card(
            problem="Missing receiver",
            cause="History needs bank and last4",
            action="Usage: /history SCB 3376",
        )
        await messaging.send_or_edit_card(update, context, text)
        return
    bank, last4 = context.args[0].upper(), context.args[1]
    profile = ledger(context).receiver_profile(bank, last4)
    if not profile:
        text = cards.error_card(
            problem="Receiver not found",
            cause=f"{bank} ••••{last4} has no settled history",
            action="Settle a transaction first",
        )
        await messaging.send_or_edit_card(update, context, text)
        return
    await messaging.send_or_edit_card(update, context, cards.history_card(profile))


async def cmd_ledger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not context.args:
        text = cards.error_card(
            problem="Missing Ledger ID",
            cause="No identifier supplied",
            action="Usage: /ledger LV-YYYYMMDD-XXXXXX",
        )
        await messaging.send_or_edit_card(update, context, text)
        return
    tx = ledger(context).get(context.args[0].upper())
    if not tx:
        text = cards.error_card(
            problem="Ledger not found",
            cause=context.args[0],
            action="Check the Ledger ID and retry",
        )
        await messaging.send_or_edit_card(update, context, text)
        return
    messaging.remember_ledger(context, tx.ledger_id)
    await messaging.send_or_edit_card(
        update, context, cards.receive_card(tx), keyboard=keyboards.confirm_keyboard(tx.ledger_id)
    )


# --- inbound media / text -----------------------------------------------

async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update) or not update.effective_message or not update.effective_user:
        return

    await messaging.show_typing(update, context)
    # Loading card first — then edit through OCR → confirmation
    context.chat_data["console"] = {}
    loading = await messaging.send_or_edit_card(update, context, cards.loading_card("RECEIVING"))

    photo = update.effective_message.photo[-1]
    tg_file = await context.bot.get_file(photo.file_id)
    image_bytes = bytes(await tg_file.download_as_bytearray())
    caption = update.effective_message.caption or ""

    await messaging.send_or_edit_card(
        update, context, cards.loading_card("OCR"), message_id=loading.message_id
    )

    result, digest = await ocr.analyze_slip(image_bytes, caption=caption)
    store = ledger(context)

    duplicate = store.find_by_slip_hash(digest)
    if duplicate and duplicate.status != TxStatus.DELETED.value:
        text = cards.error_card(
            problem="Duplicate slip",
            cause=f"Matches {duplicate.ledger_id}",
            action="Use Edit on the original or send a new slip",
        )
        await messaging.send_or_edit_card(update, context, text, message_id=loading.message_id)
        return

    tx = flow.build_from_ocr(
        store,
        result,
        slip_hash=digest,
        staff_id=update.effective_user.id,
        staff_name=update.effective_user.full_name or "",
        chat_id=update.effective_chat.id,
        image_file_id=photo.file_id,
    )
    messaging.remember_ledger(context, tx.ledger_id)

    # Repeated receiver warning folded into OCR confidence warnings display via status
    if tx.bank and tx.last4:
        prior = store.receiver_tx_count(tx.bank, tx.last4)
        if prior >= 1:
            warnings = list(tx.ocr.get("warnings") or [])
            warnings.append(f"Repeated receiver · {prior} prior")
            tx.ocr["warnings"] = warnings
            store.update(tx)

    # OCR card, then transition to confirmation (single decision screen)
    await messaging.send_or_edit_card(
        update, context, cards.ocr_card(tx), message_id=loading.message_id
    )

    # Brief progress: edit into confirmation card (one card, one decision)
    conf = cards.confirmation_card(tx)
    if result.confidence < 90:
        # Stay on confirmation but operator sees WARN in confidence field
        pass
    await messaging.send_or_edit_card(
        update,
        context,
        conf,
        keyboard=keyboards.confirm_keyboard(tx.ledger_id),
        message_id=loading.message_id,
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update) or not update.effective_message or not update.effective_user:
        return

    raw = (update.effective_message.text or "").strip()
    if not raw or raw.startswith("/"):
        return

    await messaging.show_typing(update, context)
    store = ledger(context)
    edit_mode = messaging.get_edit_mode(context)
    active_id = messaging.active_ledger_id(context)

    # Edit mode: operator sends corrected THB or receiver line
    if edit_mode and active_id:
        tx = store.get(active_id)
        if not tx:
            messaging.set_edit_mode(context, None)
            text = cards.error_card(
                problem="Ledger expired",
                cause=active_id,
                action="Send a new slip",
            )
            await messaging.send_or_edit_card(update, context, text)
            return

        if edit_mode == "thb":
            try:
                thb_val = float(
                    raw.replace(",", "")
                    .replace("THB", "")
                    .replace("thb", "")
                    .replace("บาท", "")
                    .replace("฿", "")
                    .strip()
                )
            except ValueError:
                thb_val = None
            if thb_val is None or thb_val <= 0:
                text = cards.error_card(
                    problem="Invalid THB",
                    cause=raw,
                    action="Send a numeric THB amount",
                )
                await messaging.send_or_edit_card(update, context, text)
                return
            flow.apply_thb_edit(tx, thb_val)
            if tx.ocr:
                tx.ocr["amount_thb"] = tx.thb
            store.update(tx)
            messaging.set_edit_mode(context, None)
            await messaging.send_or_edit_card(
                update,
                context,
                cards.confirmation_card(tx),
                keyboard=keyboards.confirm_keyboard(tx.ledger_id),
            )
            return

        if edit_mode == "recv":
            # Format: NAME | BANK | LAST4   or   BANK LAST4
            parts = [p.strip() for p in re.split(r"[|,/]+", raw) if p.strip()]
            if len(parts) >= 3:
                tx.receiver_name, tx.bank, tx.last4 = parts[0], parts[1].upper(), parts[2][-4:]
            elif len(parts) == 2:
                tx.bank, tx.last4 = parts[0].upper(), parts[1][-4:]
            else:
                tokens = raw.split()
                if len(tokens) >= 2 and tokens[-1].isdigit():
                    tx.last4 = tokens[-1][-4:]
                    tx.bank = tokens[-2].upper()
                    tx.receiver_name = " ".join(tokens[:-2]) or tx.receiver_name
                else:
                    tx.receiver_name = raw
            if tx.ocr:
                tx.ocr["receiver_name"] = tx.receiver_name
                tx.ocr["bank"] = tx.bank
                tx.ocr["last4"] = tx.last4
            store.update(tx)
            messaging.set_edit_mode(context, None)
            await messaging.send_or_edit_card(
                update,
                context,
                cards.confirmation_card(tx),
                keyboard=keyboards.confirm_keyboard(tx.ledger_id),
            )
            return

    # USDT amount entry
    m = USDT_RE.match(raw.strip())
    if m:
        usdt_amount = float(m.group(1))
        if usdt_amount <= 0:
            text = cards.error_card(
                problem="Invalid USDT",
                cause=raw,
                action="Send a positive USDT amount",
            )
            await messaging.send_or_edit_card(update, context, text)
            return
        context.chat_data["console"] = {}
        loading = await messaging.send_or_edit_card(update, context, cards.loading_card("QUOTING"))
        tx = flow.build_from_usdt(
            store,
            usdt_amount,
            staff_id=update.effective_user.id,
            staff_name=update.effective_user.full_name or "",
            chat_id=update.effective_chat.id,
        )
        messaging.remember_ledger(context, tx.ledger_id)
        await messaging.send_or_edit_card(
            update,
            context,
            cards.receive_card(tx),
            keyboard=keyboards.confirm_keyboard(tx.ledger_id),
            message_id=loading.message_id,
        )
        return

    # Bare THB amount (creates receive without OCR)
    try:
        maybe = float(raw.replace(",", "").replace("฿", "").strip())
    except ValueError:
        maybe = None
    if maybe and maybe >= 1 and ("thb" in raw.lower() or "บาท" in raw or "฿" in raw or maybe >= 20):
        # Treat large plain numbers / explicit THB as slip amount without image
        context.chat_data["console"] = {}
        quote = quote_from_thb(maybe)
        from ce_vault.ledger import new_ledger_id
        from ce_vault.models import Transaction

        tx = Transaction(
            ledger_id=new_ledger_id(),
            status=TxStatus.RECEIVED.value,
            thb=quote.thb,
            usdt=quote.usdt,
            buy_rate=quote.buy_rate,
            sell_rate=quote.sell_rate,
            profit_pct=quote.profit_pct,
            staff_id=update.effective_user.id,
            staff_name=update.effective_user.full_name or "",
            chat_id=update.effective_chat.id,
            confidence=0.0,
        )
        store.create(tx)
        messaging.remember_ledger(context, tx.ledger_id)
        await messaging.send_or_edit_card(
            update,
            context,
            cards.receive_card(tx),
            keyboard=keyboards.confirm_keyboard(tx.ledger_id),
        )
        return

    text = cards.error_card(
        problem="Unrecognized input",
        cause=raw[:120],
        action="Send a slip photo — or a USDT amount",
    )
    await messaging.send_or_edit_card(update, context, text)


# --- callbacks -----------------------------------------------------------

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update) or not update.callback_query:
        return
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    store = ledger(context)

    if data == "console:rates":
        await cmd_rates(update, context)
        return
    if data == "console:open":
        await cmd_start(update, context)
        return

    parts = data.split(":")
    if len(parts) < 2 or parts[0] != "tx":
        return
    action = parts[1]

    if action == "history" and len(parts) >= 4:
        bank, last4 = parts[2], parts[3]
        profile = store.receiver_profile(bank, last4)
        if not profile:
            text = cards.error_card(
                problem="Receiver not found",
                cause=f"{bank} ••••{last4}",
                action="No settled history yet",
            )
            await messaging.send_or_edit_card(update, context, text)
            return
        await messaging.send_or_edit_card(update, context, cards.history_card(profile))
        return

    if action == "done":
        await cmd_start(update, context)
        return

    if len(parts) < 3:
        return
    ledger_id = parts[2]
    tx = store.get(ledger_id)
    if not tx:
        text = cards.error_card(
            problem="Ledger not found",
            cause=ledger_id,
            action="Send a new slip",
        )
        await messaging.send_or_edit_card(update, context, text)
        return

    messaging.remember_ledger(context, ledger_id)

    if action == "confirm":
        await messaging.show_typing(update, context)
        await messaging.send_or_edit_card(update, context, cards.loading_card("SETTLING"))
        settled, balance = store.settle(ledger_id)
        await messaging.send_or_edit_card(
            update,
            context,
            cards.success_card(settled, balance_usdt=balance),
            keyboard=keyboards.success_keyboard(settled.ledger_id, settled.bank, settled.last4),
        )
        messaging.set_edit_mode(context, None)
        return

    if action == "edit":
        tx.status = TxStatus.EDITING.value
        store.update(tx)
        messaging.set_edit_mode(context, "thb")
        await messaging.send_or_edit_card(
            update, context, cards.edit_card(tx), keyboard=keyboards.edit_keyboard(tx.ledger_id)
        )
        return

    if action == "edit_thb":
        messaging.set_edit_mode(context, "thb")
        await messaging.send_or_edit_card(
            update, context, cards.edit_card(tx), keyboard=keyboards.edit_keyboard(tx.ledger_id)
        )
        return

    if action == "edit_recv":
        messaging.set_edit_mode(context, "recv")
        await messaging.send_or_edit_card(
            update, context, cards.edit_card(tx), keyboard=keyboards.edit_keyboard(tx.ledger_id)
        )
        return

    if action == "cancel":
        await messaging.send_or_edit_card(
            update, context, cards.delete_card(tx), keyboard=keyboards.delete_keyboard(tx.ledger_id)
        )
        return

    if action == "delete":
        deleted = store.soft_delete(ledger_id)
        text = cards.error_card(
            problem="Entry deleted",
            cause=deleted.ledger_id,
            action="Removed from active ledger",
        )
        await messaging.send_or_edit_card(update, context, text)
        context.chat_data["console"] = {}
        return

    if action == "keep":
        await messaging.send_or_edit_card(
            update,
            context,
            cards.confirmation_card(tx),
            keyboard=keyboards.confirm_keyboard(tx.ledger_id),
        )
        return


# --- lifecycle -----------------------------------------------------------

async def on_shutdown(application: Application) -> None:
    store: Ledger = application.bot_data.get("ledger")
    if store:
        store.close()


def build_app(token: str | None = None, db_path: str | os.PathLike | None = None) -> Application:
    application = (
        Application.builder()
        .token(token or require_telegram_token())
        .post_shutdown(on_shutdown)
        .build()
    )
    application.bot_data["ledger"] = Ledger(db_path or ledger_path())

    application.add_handler(CommandHandler(["start", "help", "console"], cmd_start))
    application.add_handler(CommandHandler("rates", cmd_rates))
    application.add_handler(CommandHandler("balance", cmd_balance))
    application.add_handler(CommandHandler("history", cmd_history))
    application.add_handler(CommandHandler("ledger", cmd_ledger))
    application.add_handler(CallbackQueryHandler(on_callback))
    application.add_handler(MessageHandler(filters.PHOTO, on_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return application


def main() -> None:
    # Optional: keep CURSOR_API_KEY unused — FinTech console is the primary product.
    # cursor_api.py remains for backward-compatible library use.
    _ = os.environ.get("CURSOR_API_KEY")
    app = build_app()
    logger.info("CE VAULT console starting")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
