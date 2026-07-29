"""CE VAULT Telegram application — FinTech Operations Console.

Not a chatbot. One card per screen. Edit-in-place. Automatic quoting.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ce_vault.config import Settings, load_settings
from ce_vault.db import LedgerStore
from ce_vault.messaging import replace_card, show_typing
from ce_vault.models import OCRResult
from ce_vault.services.ledger import LedgerService, slip_hash_bytes
from ce_vault.services.ocr import OCRService
from ce_vault.services.rates import profit_pct
from ce_vault.ui import cards, keyboards

logger = logging.getLogger("ce_vault")

USDT_AMOUNT_RE = re.compile(
    r"^(?:usdt\s*)?([0-9]+(?:\.[0-9]+)?)$",
    re.IGNORECASE,
)
THB_AMOUNT_RE = re.compile(
    r"^(?:thb\s*)?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)$",
    re.IGNORECASE,
)


# --- auth ------------------------------------------------------------------

def authorized(update: Update, settings: Settings) -> bool:
    if not settings.allowed_user_ids:
        return True
    user = update.effective_user
    return bool(user) and user.id in settings.allowed_user_ids


def staff_name(update: Update, settings: Settings) -> str:
    user = update.effective_user
    if not user:
        return settings.default_staff
    return user.username or user.full_name or settings.default_staff


def services(context: ContextTypes.DEFAULT_TYPE) -> tuple[LedgerService, OCRService, Settings]:
    return (
        context.application.bot_data["ledger"],
        context.application.bot_data["ocr"],
        context.application.bot_data["settings"],
    )


def pending(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.chat_data.setdefault("pending", {})


# --- commands --------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    if not authorized(update, settings):
        return
    ledger, _, _ = services(context)
    buy, sell = ledger.current_rates()
    text = cards.console_home(
        buy,
        sell,
        open_count=ledger.store.count_open(),
        settled_today=ledger.store.count_settled_today(),
    )
    assert update.effective_chat
    await replace_card(context, chat_id=update.effective_chat.id, text=text, message_id=None)


async def cmd_rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    if not authorized(update, settings):
        return
    ledger, _, _ = services(context)
    assert update.effective_chat
    chat_id = update.effective_chat.id

    if context.args and len(context.args) >= 2:
        try:
            buy = float(context.args[0])
            sell = float(context.args[1])
            if buy <= 0 or sell <= 0:
                raise ValueError("rates must be positive")
            ledger.set_rates(buy, sell)
        except ValueError:
            await replace_card(
                context,
                chat_id=chat_id,
                text=cards.error_card(
                    problem="Invalid rates",
                    cause="Buy/Sell must be positive numbers",
                    action="Use /rates <buy> <sell>",
                ),
                message_id=None,
            )
            return

    buy, sell = ledger.current_rates()
    await replace_card(
        context,
        chat_id=chat_id,
        text=cards.rates_card(buy, sell, profit_pct(buy, sell)),
        message_id=None,
    )


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    if not authorized(update, settings):
        return
    ledger, _, _ = services(context)
    assert update.effective_chat
    chat_id = update.effective_chat.id

    bank, last4 = _parse_receiver_args(context.args or [])
    if not bank or not last4:
        # Try last pending / last tx
        recent = ledger.store.list_recent(1)
        if recent and recent[0].bank and recent[0].last4:
            bank, last4 = recent[0].bank, recent[0].last4
        else:
            await replace_card(
                context,
                chat_id=chat_id,
                text=cards.error_card(
                    problem="Missing counterparty",
                    cause="Bank and last4 not provided",
                    action="Use /history SCB 3376",
                ),
                message_id=None,
            )
            return

    hist = ledger.store.receiver_history(bank.upper(), last4)
    if not hist:
        await replace_card(
            context,
            chat_id=chat_id,
            text=cards.error_card(
                problem="No history",
                cause=f"No ledger entries for {bank.upper()} ••••{last4}",
                action="Complete a settlement first",
            ),
            message_id=None,
        )
        return

    await replace_card(
        context,
        chat_id=chat_id,
        text=cards.history_card(hist),
        message_id=None,
    )


async def cmd_ledger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    if not authorized(update, settings):
        return
    ledger, _, _ = services(context)
    assert update.effective_chat
    chat_id = update.effective_chat.id

    if not context.args:
        await replace_card(
            context,
            chat_id=chat_id,
            text=cards.error_card(
                problem="Missing ledger id",
                cause="No ID supplied",
                action="Use /ledger LD-…",
            ),
            message_id=None,
        )
        return

    tx = ledger.store.get(context.args[0].upper())
    if not tx:
        # also try as-is
        tx = ledger.store.get(context.args[0])
    if not tx:
        await replace_card(
            context,
            chat_id=chat_id,
            text=cards.error_card(
                problem="Ledger not found",
                cause=context.args[0],
                action="Check ID and retry",
            ),
            message_id=None,
        )
        return

    await _render_tx_card(context, chat_id, tx)


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    if not authorized(update, settings):
        return
    ledger, _, _ = services(context)
    assert update.effective_chat
    from ce_vault.models import Transaction, iso

    bal = ledger.store.get_balance()
    buy, sell = ledger.current_rates()
    stub = Transaction(
        ledger_id="BAL-LEDGER",
        status="SETTLED",
        usdt=bal,
        profit_pct=profit_pct(buy, sell),
        created_at=iso(),
        updated_at=iso(),
    )
    await replace_card(
        context,
        chat_id=update.effective_chat.id,
        text=cards.success_card(stub, updated_balance_usdt=bal),
        message_id=None,
    )


# --- intake: photo / text --------------------------------------------------

async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    if not authorized(update, settings):
        return
    ledger, ocr, _ = services(context)
    assert update.effective_chat and update.effective_message
    chat_id = update.effective_chat.id
    message = update.effective_message

    await show_typing(context, chat_id)

    photo = message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    data = bytes(await file.download_as_bytearray())
    digest = slip_hash_bytes(data)

    dup = ledger.check_duplicate_slip(digest)
    console_id = await replace_card(
        context,
        chat_id=chat_id,
        text=cards.loading_card("Ingesting slip", 0.2),
        message_id=None,
    )

    if dup and dup.status != "VOID":
        await replace_card(
            context,
            chat_id=chat_id,
            message_id=console_id,
            text=cards.error_card(
                problem="Duplicate slip",
                cause=f"Matches {dup.ledger_id}",
                action="Use existing ledger or void the prior entry",
                ledger_id=dup.ledger_id,
            ),
        )
        return

    tx = ledger.create_from_slip(
        staff=staff_name(update, settings),
        staff_id=update.effective_user.id if update.effective_user else None,
        chat_id=chat_id,
        slip_hash=digest,
    )
    image_path = ledger.save_image(data, tx.ledger_id, suffix=".jpg")
    tx.image_path = str(image_path)
    tx.message_id = console_id
    ledger.store.upsert(tx)

    await replace_card(
        context,
        chat_id=chat_id,
        message_id=console_id,
        text=cards.receive_card(tx, progress=0.45),
    )

    await show_typing(context, chat_id)
    await replace_card(
        context,
        chat_id=chat_id,
        message_id=console_id,
        text=cards.loading_card("Vision", 0.7, ledger_id=tx.ledger_id),
    )

    caption = message.caption or ""
    result = await ocr.extract(image_path=Path(image_path), caption=caption)
    tx = ledger.apply_ocr(tx, result)

    repeats = ledger.repeated_receiver(tx.bank, tx.last4)
    note = ""
    if repeats > 1:
        note = f"\n\n<i>Counterparty</i>\n<code>{repeats} prior settlements</code>"

    await replace_card(
        context,
        chat_id=chat_id,
        message_id=console_id,
        text=cards.ocr_card(tx, result) + note,
        keyboard=keyboards.ocr_keyboard(tx.ledger_id),
    )
    tx.message_id = console_id
    ledger.store.upsert(tx)
    pending(context)["active_ledger"] = tx.ledger_id


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    if not authorized(update, settings):
        return
    ledger, ocr, _ = services(context)
    assert update.effective_chat and update.effective_message
    chat_id = update.effective_chat.id
    text = (update.effective_message.text or "").strip()
    if not text or text.startswith("/"):
        return

    state = pending(context)

    # Edit flow: awaiting a field value
    if state.get("edit_ledger") and state.get("edit_field"):
        await _apply_edit(update, context, text)
        return

    # USDT amount intake
    m = USDT_AMOUNT_RE.match(text)
    if m and ("usdt" in text.lower() or "." in m.group(1)):
        usdt = float(m.group(1))
        await _intake_usdt(update, context, usdt)
        return

    # Bare number with usdt keyword nearby handled above; also accept "12.5 USDT"
    m2 = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*usdt$", text, re.IGNORECASE)
    if m2:
        await _intake_usdt(update, context, float(m2.group(1)))
        return

    # Slip text paste → heuristic OCR path (no image)
    if _looks_like_slip_text(text):
        await _intake_slip_text(update, context, text)
        return

    # THB bare amount as quick quote confirmation seed
    m3 = THB_AMOUNT_RE.match(text.replace(",", ""))
    if m3 and state.get("active_ledger"):
        tx = ledger.store.get(state["active_ledger"])
        if tx and tx.status != "SETTLED":
            thb = float(m3.group(1).replace(",", ""))
            tx = ledger.requote_thb(tx, thb)
            await _render_tx_card(context, chat_id, tx, message_id=tx.message_id)
            return

    await replace_card(
        context,
        chat_id=chat_id,
        text=cards.error_card(
            problem="Unrecognized input",
            cause="Console expects a slip or USDT amount",
            action="Send slip photo · or 12.5 USDT",
        ),
        message_id=None,
    )


async def _intake_usdt(update: Update, context: ContextTypes.DEFAULT_TYPE, usdt: float) -> None:
    ledger, _, settings = services(context)
    assert update.effective_chat
    chat_id = update.effective_chat.id
    await show_typing(context, chat_id)

    mid = await replace_card(
        context,
        chat_id=chat_id,
        text=cards.loading_card("Quoting", 0.5),
        message_id=None,
    )
    tx = ledger.create_from_usdt(
        usdt=usdt,
        staff=staff_name(update, settings),
        staff_id=update.effective_user.id if update.effective_user else None,
        chat_id=chat_id,
    )
    tx.message_id = mid
    ledger.store.upsert(tx)
    pending(context)["active_ledger"] = tx.ledger_id
    await replace_card(
        context,
        chat_id=chat_id,
        message_id=mid,
        text=cards.confirmation_card(tx),
        keyboard=keyboards.confirm_keyboard(tx.ledger_id),
    )


async def _intake_slip_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    ledger, ocr, settings = services(context)
    assert update.effective_chat
    chat_id = update.effective_chat.id
    await show_typing(context, chat_id)

    digest = slip_hash_bytes(text.encode("utf-8"))
    dup = ledger.check_duplicate_slip(digest)
    mid = await replace_card(
        context,
        chat_id=chat_id,
        text=cards.loading_card("Parsing slip", 0.4),
        message_id=None,
    )
    if dup and dup.status != "VOID":
        await replace_card(
            context,
            chat_id=chat_id,
            message_id=mid,
            text=cards.error_card(
                problem="Duplicate slip",
                cause=f"Matches {dup.ledger_id}",
                action="Use existing ledger or void the prior entry",
                ledger_id=dup.ledger_id,
            ),
        )
        return

    tx = ledger.create_from_slip(
        staff=staff_name(update, settings),
        staff_id=update.effective_user.id if update.effective_user else None,
        chat_id=chat_id,
        slip_hash=digest,
    )
    tx.message_id = mid
    result = await ocr.extract(caption=text, hint_text=text)
    tx = ledger.apply_ocr(tx, result)
    repeats = ledger.repeated_receiver(tx.bank, tx.last4)
    note = ""
    if repeats > 1:
        note = f"\n\n<i>Counterparty</i>\n<code>{repeats} prior settlements</code>"
    await replace_card(
        context,
        chat_id=chat_id,
        message_id=mid,
        text=cards.ocr_card(tx, result) + note,
        keyboard=keyboards.ocr_keyboard(tx.ledger_id),
    )
    pending(context)["active_ledger"] = tx.ledger_id


# --- callbacks -------------------------------------------------------------

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    if not authorized(update, settings):
        return
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    ledger, _, _ = services(context)
    assert update.effective_chat
    chat_id = update.effective_chat.id
    data = query.data

    if data == "console:home":
        buy, sell = ledger.current_rates()
        await replace_card(
            context,
            chat_id=chat_id,
            message_id=query.message.message_id if query.message else None,
            text=cards.console_home(
                buy,
                sell,
                open_count=ledger.store.count_open(),
                settled_today=ledger.store.count_settled_today(),
            ),
        )
        return

    parts = data.split(":")
    if len(parts) < 3 or parts[0] != "tx":
        return
    action = parts[1]
    ledger_id = parts[2]
    tx = ledger.store.get(ledger_id)
    if not tx:
        await replace_card(
            context,
            chat_id=chat_id,
            message_id=query.message.message_id if query.message else None,
            text=cards.error_card(
                problem="Ledger not found",
                cause=ledger_id,
                action="Restart intake",
            ),
        )
        return

    mid = query.message.message_id if query.message else tx.message_id

    if action == "quote":
        # OCR → Confirmation (one decision)
        await replace_card(
            context,
            chat_id=chat_id,
            message_id=mid,
            text=cards.confirmation_card(tx),
            keyboard=keyboards.confirm_keyboard(tx.ledger_id),
        )
        return

    if action == "confirm":
        tx = ledger.confirm(tx)
        await replace_card(
            context,
            chat_id=chat_id,
            message_id=mid,
            text=cards.confirmation_card(tx),
            keyboard=keyboards.settle_keyboard(tx.ledger_id),
        )
        return

    if action == "settle":
        await show_typing(context, chat_id)
        tx, bal = ledger.settle(tx)
        await replace_card(
            context,
            chat_id=chat_id,
            message_id=mid,
            text=cards.success_card(tx, updated_balance_usdt=bal),
            keyboard=keyboards.done_keyboard(),
        )
        pending(context).pop("active_ledger", None)
        return

    if action == "edit":
        await replace_card(
            context,
            chat_id=chat_id,
            message_id=mid,
            text=cards.edit_card(tx),
            keyboard=keyboards.edit_field_keyboard(tx.ledger_id),
        )
        return

    if action == "editfield" and len(parts) >= 4:
        field = parts[3]
        pending(context)["edit_ledger"] = tx.ledger_id
        pending(context)["edit_field"] = field
        await replace_card(
            context,
            chat_id=chat_id,
            message_id=mid,
            text=cards.edit_card(tx, field=field),
        )
        return

    if action == "back":
        pending(context).pop("edit_ledger", None)
        pending(context).pop("edit_field", None)
        await replace_card(
            context,
            chat_id=chat_id,
            message_id=mid,
            text=cards.confirmation_card(tx),
            keyboard=keyboards.confirm_keyboard(tx.ledger_id),
        )
        return

    if action == "cancel":
        tx = ledger.void(tx)
        await replace_card(
            context,
            chat_id=chat_id,
            message_id=mid,
            text=cards.error_card(
                problem="Cancelled",
                cause="Operator voided intake",
                action="Send a new slip or USDT amount",
                ledger_id=tx.ledger_id,
            ),
            keyboard=keyboards.done_keyboard(),
        )
        pending(context).pop("active_ledger", None)
        return

    if action == "delete":
        await replace_card(
            context,
            chat_id=chat_id,
            message_id=mid,
            text=cards.delete_card(tx),
            keyboard=keyboards.delete_keyboard(tx.ledger_id),
        )
        return

    if action == "void":
        tx = ledger.void(tx)
        await replace_card(
            context,
            chat_id=chat_id,
            message_id=mid,
            text=cards.error_card(
                problem="Voided",
                cause="Ledger entry removed from active book",
                action="Send a new slip or USDT amount",
                ledger_id=tx.ledger_id,
            ),
            keyboard=keyboards.done_keyboard(),
        )
        pending(context).pop("active_ledger", None)
        return


async def _apply_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    ledger, _, _ = services(context)
    assert update.effective_chat
    chat_id = update.effective_chat.id
    state = pending(context)
    tx = ledger.store.get(state["edit_ledger"])
    if not tx:
        state.clear()
        return
    field = state["edit_field"]
    try:
        if field == "amount":
            thb = float(text.replace(",", "").replace("THB", "").strip())
            tx = ledger.requote_thb(tx, thb)
        elif field == "usdt":
            usdt = float(text.replace(",", "").replace("USDT", "").strip())
            tx = ledger.requote_usdt(tx, usdt)
        elif field == "receiver":
            tx = ledger.update_receiver(tx, receiver_name=text.strip())
        elif field == "bank":
            tx = ledger.update_receiver(tx, bank=text.strip())
        elif field == "last4":
            digits = re.sub(r"\D", "", text)[-4:]
            if len(digits) != 4:
                raise ValueError("last4")
            tx = ledger.update_receiver(tx, last4=digits)
        else:
            raise ValueError("field")
    except ValueError:
        await replace_card(
            context,
            chat_id=chat_id,
            message_id=tx.message_id,
            text=cards.error_card(
                problem="Invalid value",
                cause=f"Could not parse {field}",
                action="Send a clean value",
                ledger_id=tx.ledger_id,
            ),
        )
        return

    state.pop("edit_ledger", None)
    state.pop("edit_field", None)
    await replace_card(
        context,
        chat_id=chat_id,
        message_id=tx.message_id,
        text=cards.confirmation_card(tx),
        keyboard=keyboards.confirm_keyboard(tx.ledger_id),
    )


# --- helpers ---------------------------------------------------------------

async def _render_tx_card(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    tx,
    message_id: int | None = None,
) -> None:
    if tx.status == "SETTLED":
        bal = context.application.bot_data["ledger"].store.get_balance()
        await replace_card(
            context,
            chat_id=chat_id,
            message_id=message_id,
            text=cards.success_card(tx, updated_balance_usdt=bal),
            keyboard=keyboards.done_keyboard(),
        )
    elif tx.status == "WAITING USDT":
        await replace_card(
            context,
            chat_id=chat_id,
            message_id=message_id,
            text=cards.confirmation_card(tx),
            keyboard=keyboards.settle_keyboard(tx.ledger_id),
        )
    else:
        await replace_card(
            context,
            chat_id=chat_id,
            message_id=message_id,
            text=cards.confirmation_card(tx),
            keyboard=keyboards.confirm_keyboard(tx.ledger_id),
        )


def _parse_receiver_args(args: list[str]) -> tuple[str | None, str | None]:
    if len(args) >= 2:
        return args[0], re.sub(r"\D", "", args[1])[-4:] or None
    if len(args) == 1 and "•" in args[0]:
        # SCB••••3376 style
        m = re.match(r"([A-Za-z]+).*?([0-9]{4})$", args[0])
        if m:
            return m.group(1), m.group(2)
    return None, None


def _looks_like_slip_text(text: str) -> bool:
    lower = text.lower()
    markers = ("scb", "kbank", "บาท", "thb", "โอน", "บัญชี", "นาย", "นาง", "xxxx", "••••")
    return any(m in lower or m in text for m in markers) and len(text) >= 8


# --- lifecycle -------------------------------------------------------------

async def on_shutdown(application: Application) -> None:
    store: LedgerStore = application.bot_data["store"]
    store.close()


def build_app(settings: Settings | None = None) -> Application:
    settings = settings or load_settings()
    if not settings.telegram_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN must be set")

    settings.images_dir.mkdir(parents=True, exist_ok=True)
    store = LedgerStore(settings.db_path)
    ledger = LedgerService(store, settings)
    ocr = OCRService(settings)

    application = (
        Application.builder()
        .token(settings.telegram_token)
        .post_shutdown(on_shutdown)
        .build()
    )
    application.bot_data["settings"] = settings
    application.bot_data["store"] = store
    application.bot_data["ledger"] = ledger
    application.bot_data["ocr"] = ocr

    application.add_handler(CommandHandler(["start", "help", "console"], cmd_start))
    application.add_handler(CommandHandler("rates", cmd_rates))
    application.add_handler(CommandHandler("history", cmd_history))
    application.add_handler(CommandHandler("ledger", cmd_ledger))
    application.add_handler(CommandHandler("balance", cmd_balance))
    application.add_handler(CallbackQueryHandler(on_callback))
    application.add_handler(MessageHandler(filters.PHOTO, on_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return application


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        level=logging.INFO,
    )
    # Optional dotenv
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    app = build_app()
    logger.info("CE VAULT console starting")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
