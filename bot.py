"""CE VAULT — Premium FinTech Operations Console for Telegram.

Design language: dark OLED terminal. One card per message. One decision
per screen. Edit-in-place instead of message spam. Monospace numbers.
Operators provide a slip image OR a USDT amount — everything else is
derived from the rate desk automatically.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from telegram import Message, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from vault import cards
from vault.keyboards import (
    confirm_keyboard,
    delete_keyboard,
    done_keyboard,
    edit_fields_keyboard,
    settle_keyboard,
)
from vault.ledger import Ledger
from vault.ocr import DEMO_SLIP_TEXT, analyze_slip, parse_slip_text
from vault.rates import RateQuote, compute_from_thb, compute_from_usdt
from vault.theme import Status

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO
)
logger = logging.getLogger("ce_vault")

LEDGER_PATH = Path(os.environ.get("LEDGER_DB", "data/vault.db"))
USDT_AMOUNT_RE = re.compile(
    r"^(?:usdt\s*)?([0-9]+(?:\.[0-9]+)?)\s*(?:usdt)?$", re.I
)


# --- auth ----------------------------------------------------------------

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


def quote(context: ContextTypes.DEFAULT_TYPE) -> RateQuote:
    buy, sell = ledger(context).get_rates()
    return RateQuote(buy_rate=buy, sell_rate=sell)


# --- message UX: edit-in-place -------------------------------------------

async def send_card(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup=None,
    *,
    edit_message_id: int | None = None,
) -> Message:
    """Prefer editing an existing console message; otherwise send new."""
    assert update.effective_chat
    chat_id = update.effective_chat.id
    mid = edit_message_id or context.user_data.get("console_message_id")

    if mid:
        try:
            msg = await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=mid,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
            context.user_data["console_message_id"] = msg.message_id
            return msg
        except Exception as exc:
            logger.debug("edit failed, sending new: %s", exc)

    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )
    context.user_data["console_message_id"] = msg.message_id
    return msg


async def show_loading(
    update: Update, context: ContextTypes.DEFAULT_TYPE, stage: str, progress: int | None = None
) -> Message:
    if update.effective_chat:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    return await send_card(update, context, cards.loading_card(stage=stage, progress=progress))


def parse_status(value: str | None) -> Status:
    if not value:
        return Status.RECEIVED
    for item in Status:
        if item.value == value or item.name == value:
            return item
    return Status.RECEIVED


def tx_card_text(entry: dict, status: Status | None = None) -> str:
    st = status or parse_status(entry.get("status"))
    return cards.receive_card(
        ledger_id=entry["id"],
        thb=entry.get("thb"),
        usdt=entry.get("usdt"),
        buy_rate=entry.get("buy_rate"),
        sell_rate=entry.get("sell_rate"),
        profit=entry.get("profit_pct"),
        receiver=entry.get("receiver_name"),
        bank=entry.get("bank"),
        last4=entry.get("last4"),
        conf=entry.get("ocr_confidence"),
        status=st,
    )


# --- intake: slip photo or USDT amount -----------------------------------

async def begin_from_ocr(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    text: str | None = None,
    image_bytes: bytes | None = None,
    file_id: str | None = None,
    file_unique_id: str | None = None,
) -> None:
    user = update.effective_user
    assert user and update.effective_chat

    await show_loading(update, context, "Ingesting slip", 15)
    await show_loading(update, context, "Vision pass", 45)

    result, digest = await analyze_slip(
        text=text, image_bytes=image_bytes, file_unique_id=file_unique_id
    )

    store = ledger(context)
    duplicate = store.find_by_slip_hash(digest)
    repeat = store.is_repeat_receiver(result.bank, result.last4)

    await show_loading(update, context, "Building ledger", 75)

    q = quote(context)
    amounts = compute_from_thb(result.amount_thb, q) if result.amount_thb else {
        "thb": None,
        "usdt": None,
        "buy_rate": q.buy_rate,
        "sell_rate": q.sell_rate,
        "profit_pct": round(q.profit_pct, 2),
    }

    entry = store.create_entry(
        status=Status.OCR_VERIFIED.value if result.amount_thb else Status.RECEIVED.value,
        slip_file_id=file_id,
        slip_hash=digest,
        ocr=result.to_dict(),
        ocr_confidence=result.confidence,
        receiver_name=result.receiver_name,
        bank=result.bank,
        last4=result.last4,
        thb=amounts.get("thb"),
        usdt=amounts.get("usdt"),
        buy_rate=amounts.get("buy_rate"),
        sell_rate=amounts.get("sell_rate"),
        profit_pct=amounts.get("profit_pct"),
        staff_id=user.id,
        staff_name=user.full_name,
        chat_id=update.effective_chat.id,
    )
    context.user_data["active_ledger_id"] = entry["id"]
    context.user_data.pop("edit_field", None)

    # OCR card first (edit-in-place), then transition to confirmation card
    ocr_text = cards.ocr_card(
        ledger_id=entry["id"],
        vision=result.confidence,
        receiver=result.receiver_name,
        bank=result.bank,
        last4=result.last4,
        amount=result.amount_thb,
        verified=bool(result.amount_thb and result.bank and result.last4),
        duplicate=bool(duplicate),
        repeat_receiver=repeat,
    )
    await send_card(update, context, ocr_text)

    # Brief progress then confirmation decision card
    await show_loading(update, context, "Preparing confirmation", 92)
    await send_card(
        update,
        context,
        tx_card_text(entry, Status.OCR_VERIFIED),
        reply_markup=confirm_keyboard(entry["id"]),
    )


async def begin_from_usdt(
    update: Update, context: ContextTypes.DEFAULT_TYPE, usdt_amount: float
) -> None:
    user = update.effective_user
    assert user and update.effective_chat

    await show_loading(update, context, "Calculating", 40)
    q = quote(context)
    amounts = compute_from_usdt(usdt_amount, q)
    store = ledger(context)
    entry = store.create_entry(
        status=Status.RECEIVED.value,
        thb=amounts["thb"],
        usdt=amounts["usdt"],
        buy_rate=amounts["buy_rate"],
        sell_rate=amounts["sell_rate"],
        profit_pct=amounts["profit_pct"],
        staff_id=user.id,
        staff_name=user.full_name,
        chat_id=update.effective_chat.id,
    )
    context.user_data["active_ledger_id"] = entry["id"]
    await send_card(
        update,
        context,
        tx_card_text(entry, Status.RECEIVED),
        reply_markup=confirm_keyboard(entry["id"]),
    )


# --- commands ------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    context.user_data.pop("console_message_id", None)
    await send_card(update, context, cards.welcome_card())


async def cmd_rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    q = quote(context)
    bal = ledger(context).get_balance()
    await send_card(
        update,
        context,
        cards.rates_card(buy=q.buy_rate, sell=q.sell_rate, profit=q.profit_pct, balance=bal),
    )


async def cmd_setrates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not context.args or len(context.args) < 2:
        await send_card(
            update,
            context,
            cards.error_card(
                problem="Missing rates",
                cause="Buy and sell rates were not provided",
                action="Use /setrates <buy> <sell>",
            ),
        )
        return
    try:
        buy = float(context.args[0])
        sell = float(context.args[1])
        if buy <= 0 or sell <= 0:
            raise ValueError("rates must be positive")
    except ValueError:
        await send_card(
            update,
            context,
            cards.error_card(
                problem="Invalid rates",
                cause="Values must be positive numbers",
                action="Example: /setrates 39.89 40.00",
            ),
        )
        return
    user = update.effective_user
    ledger(context).set_rates(buy, sell, updated_by=user.id if user else None)
    q = quote(context)
    await send_card(
        update,
        context,
        cards.rates_card(buy=q.buy_rate, sell=q.sell_rate, profit=q.profit_pct),
    )


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if context.args:
        try:
            value = float(context.args[0])
            ledger(context).set_balance(value)
        except ValueError:
            await send_card(
                update,
                context,
                cards.error_card(
                    problem="Invalid balance",
                    cause="Balance must be numeric",
                    action="Use /balance <usdt>",
                ),
            )
            return
    q = quote(context)
    bal = ledger(context).get_balance()
    await send_card(
        update,
        context,
        cards.rates_card(buy=q.buy_rate, sell=q.sell_rate, profit=q.profit_pct, balance=bal),
    )


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    store = ledger(context)
    if context.args:
        # /history SCB 3376  OR  /history SCB••••3376
        raw = " ".join(context.args)
        parts = re.findall(r"[A-Za-z]+|\d{4}", raw)
        bank = next((p.upper() for p in parts if p.isalpha()), None)
        last4 = next((p for p in parts if p.isdigit() and len(p) == 4), None)
        hist = store.receiver_history(bank, last4)
        if not hist:
            await send_card(
                update,
                context,
                cards.error_card(
                    problem="Receiver not found",
                    cause=f"No history for {bank or '?'} ••••{last4 or '????'}",
                    action="Settle a transaction first",
                ),
            )
            return
        await send_card(
            update,
            context,
            cards.history_card(
                bank=hist["bank"],
                last4=hist["last4"],
                name=hist.get("name"),
                tx_count=hist["tx_count"],
                total_thb=hist["total_thb"],
                total_usdt=hist["total_usdt"],
                first_seen=hist["first_seen"],
                last_seen=hist["last_seen"],
                risk=hist["risk"],
            ),
        )
        return

    # Default: active entry's receiver, else recent ledger list
    active_id = context.user_data.get("active_ledger_id")
    if active_id:
        entry = store.get(active_id)
        if entry and entry.get("bank") and entry.get("last4"):
            hist = store.receiver_history(entry["bank"], entry["last4"])
            if hist:
                await send_card(
                    update,
                    context,
                    cards.history_card(
                        bank=hist["bank"],
                        last4=hist["last4"],
                        name=hist.get("name"),
                        tx_count=hist["tx_count"],
                        total_thb=hist["total_thb"],
                        total_usdt=hist["total_usdt"],
                        first_seen=hist["first_seen"],
                        last_seen=hist["last_seen"],
                        risk=hist["risk"],
                    ),
                )
                return

    rows = store.list_recent(8)
    await send_card(update, context, cards.ledger_list_card(rows))


async def cmd_ledger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not context.args:
        rows = ledger(context).list_recent(10)
        await send_card(update, context, cards.ledger_list_card(rows))
        return
    entry = ledger(context).get(context.args[0].upper())
    if not entry:
        # try as-is
        entry = ledger(context).get(context.args[0])
    if not entry:
        await send_card(
            update,
            context,
            cards.error_card(
                problem="Ledger not found",
                cause=f"No entry {context.args[0]}",
                action="Use /ledger for recent entries",
            ),
        )
        return
    status = parse_status(entry.get("status"))
    kb = None
    if status in (Status.RECEIVED, Status.OCR_VERIFIED):
        kb = confirm_keyboard(entry["id"])
    elif status == Status.WAITING_USDT:
        kb = settle_keyboard(entry["id"])
    elif status == Status.SETTLED:
        kb = done_keyboard()
    await send_card(update, context, tx_card_text(entry, status), reply_markup=kb)


async def cmd_demo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Offline demo using a fixture slip — no image required."""
    if not authorized(update):
        return
    await begin_from_ocr(update, context, text=DEMO_SLIP_TEXT, file_unique_id="demo-slip-v1")


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not context.args:
        await send_card(
            update,
            context,
            cards.error_card(
                problem="Missing ledger id",
                cause="No target specified",
                action="Use /delete <ledger-id>",
            ),
        )
        return
    entry_id = context.args[0]
    entry = ledger(context).get(entry_id)
    if not entry:
        await send_card(
            update,
            context,
            cards.error_card(
                problem="Ledger not found",
                cause=f"No entry {entry_id}",
                action="Check /ledger",
            ),
        )
        return
    summary = f"{entry.get('thb') or '—'} THB · {entry.get('status')}"
    await send_card(
        update,
        context,
        cards.delete_card(ledger_id=entry["id"], summary=summary),
        reply_markup=delete_keyboard(entry["id"]),
    )


# --- message handlers ----------------------------------------------------

async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    assert update.effective_message and update.effective_message.photo
    # Clear previous console message so a new intake starts clean
    context.user_data.pop("console_message_id", None)
    photo = update.effective_message.photo[-1]
    tg_file = await context.bot.get_file(photo.file_id)
    image_bytes = bytes(await tg_file.download_as_bytearray())
    caption = update.effective_message.caption
    await begin_from_ocr(
        update,
        context,
        text=caption,
        image_bytes=image_bytes,
        file_id=photo.file_id,
        file_unique_id=photo.file_unique_id,
    )


async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    assert update.effective_message and update.effective_message.document
    doc = update.effective_message.document
    if not (doc.mime_type or "").startswith("image/"):
        await send_card(
            update,
            context,
            cards.error_card(
                problem="Unsupported file",
                cause="Only image slips are accepted",
                action="Send a JPG/PNG slip",
            ),
        )
        return
    context.user_data.pop("console_message_id", None)
    tg_file = await context.bot.get_file(doc.file_id)
    image_bytes = bytes(await tg_file.download_as_bytearray())
    await begin_from_ocr(
        update,
        context,
        text=update.effective_message.caption,
        image_bytes=image_bytes,
        file_id=doc.file_id,
        file_unique_id=doc.file_unique_id,
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    assert update.effective_message and update.effective_message.text
    text = update.effective_message.text.strip()

    # Edit-mode field capture
    edit_field = context.user_data.get("edit_field")
    active_id = context.user_data.get("active_ledger_id")
    if edit_field and active_id:
        await apply_edit(update, context, active_id, edit_field, text)
        return

    # USDT amount shortcut
    m = USDT_AMOUNT_RE.match(text)
    if m:
        context.user_data.pop("console_message_id", None)
        await begin_from_usdt(update, context, float(m.group(1)))
        return

    # Treat multi-line / bank-like text as a pasted slip
    if len(text) > 40 or any(k in text for k in ("บาท", "THB", "SCB", "โอน", "จำนวน")):
        context.user_data.pop("console_message_id", None)
        await begin_from_ocr(update, context, text=text, file_unique_id=f"text:{hash(text)}")
        return

    await send_card(
        update,
        context,
        cards.error_card(
            problem="Unrecognized input",
            cause="Expected a slip image or USDT amount",
            action="Send photo, paste slip text, or type e.g. 12.5",
        ),
    )


async def apply_edit(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    entry_id: str,
    field: str,
    value: str,
) -> None:
    store = ledger(context)
    entry = store.get(entry_id)
    if not entry:
        await send_card(
            update,
            context,
            cards.error_card(
                problem="Ledger not found",
                cause=entry_id,
                action="Start a new entry",
            ),
        )
        return

    updates: dict = {}
    try:
        if field == "thb":
            thb = float(value.replace(",", ""))
            amounts = compute_from_thb(thb, quote(context))
            updates.update(amounts)
        elif field == "usdt":
            usdt = float(value.replace(",", ""))
            amounts = compute_from_usdt(usdt, quote(context))
            updates.update(amounts)
        elif field == "receiver":
            updates["receiver_name"] = value.strip()
        elif field == "bank":
            updates["bank"] = value.strip().upper()
        elif field == "last4":
            digits = re.sub(r"\D", "", value)[-4:]
            if len(digits) != 4:
                raise ValueError("last4 requires 4 digits")
            updates["last4"] = digits
        else:
            raise ValueError(f"unknown field {field}")
    except ValueError as exc:
        await send_card(
            update,
            context,
            cards.error_card(
                problem="Invalid edit",
                cause=str(exc),
                action="Send a valid value",
            ),
        )
        return

    entry = store.update(entry_id, **updates) or entry
    context.user_data.pop("edit_field", None)
    status = parse_status(entry.get("status"))
    await send_card(
        update,
        context,
        tx_card_text(entry, status),
        reply_markup=confirm_keyboard(entry_id),
    )


# --- callbacks -----------------------------------------------------------

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    query = update.callback_query
    assert query and query.data
    await query.answer()
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    namespace, action = parts[0], parts[1]
    entry_id = parts[2] if len(parts) > 2 else None

    # Keep edits targeting the console message that holds the buttons
    if query.message:
        context.user_data["console_message_id"] = query.message.message_id

    store = ledger(context)

    if namespace == "tx" and action == "new":
        context.user_data.pop("console_message_id", None)
        context.user_data.pop("active_ledger_id", None)
        await send_card(update, context, cards.welcome_card())
        return

    if not entry_id:
        return

    entry = store.get(entry_id)
    if not entry and action != "delete":
        await send_card(
            update,
            context,
            cards.error_card(
                problem="Ledger not found",
                cause=entry_id,
                action="Start a new entry",
            ),
        )
        return

    if namespace == "tx" and action == "confirm" and entry:
        store.update(entry_id, status=Status.WAITING_USDT.value)
        entry = store.get(entry_id) or entry
        await send_card(
            update,
            context,
            tx_card_text(entry, Status.WAITING_USDT),
            reply_markup=settle_keyboard(entry_id),
        )
        return

    if namespace == "tx" and action == "settle" and entry:
        await show_loading(update, context, "Settling", 60)
        settled = store.record_settlement(entry_id)
        bal = store.get_balance()
        assert settled
        await send_card(
            update,
            context,
            cards.success_card(
                ledger_id=settled["id"],
                profit=settled.get("profit_pct"),
                balance_usdt=bal,
                thb=settled.get("thb"),
                usdt=settled.get("usdt"),
            ),
            reply_markup=done_keyboard(),
        )
        return

    if namespace == "tx" and action == "cancel" and entry:
        store.update(entry_id, status=Status.CANCELLED.value)
        await send_card(
            update,
            context,
            cards.error_card(
                problem="Cancelled",
                cause=f"{entry_id} discarded",
                action="Send a new slip or USDT amount",
            ),
        )
        context.user_data.pop("active_ledger_id", None)
        return

    if namespace == "tx" and action == "edit" and entry:
        await send_card(
            update,
            context,
            cards.edit_card(
                ledger_id=entry_id,
                field="Select",
                current="—",
                hint="Choose a field below",
            ),
            reply_markup=edit_fields_keyboard(entry_id),
        )
        return

    if namespace == "tx" and action == "back" and entry:
        status = parse_status(entry.get("status"))
        kb = confirm_keyboard(entry_id)
        if status == Status.WAITING_USDT:
            kb = settle_keyboard(entry_id)
        await send_card(update, context, tx_card_text(entry, status), reply_markup=kb)
        return

    if namespace == "tx" and action == "delete":
        if entry:
            store.delete(entry_id)
        await send_card(
            update,
            context,
            cards.error_card(
                problem="Deleted",
                cause=f"{entry_id} removed from ledger",
                action="Send a new slip or USDT amount",
            ),
            reply_markup=done_keyboard(),
        )
        context.user_data.pop("active_ledger_id", None)
        return

    if namespace == "edit" and entry:
        field = action
        context.user_data["edit_field"] = field
        context.user_data["active_ledger_id"] = entry_id
        current_map = {
            "thb": entry.get("thb"),
            "usdt": entry.get("usdt"),
            "receiver": entry.get("receiver_name"),
            "bank": entry.get("bank"),
            "last4": entry.get("last4"),
        }
        hints = {
            "thb": "Send THB amount",
            "usdt": "Send USDT amount",
            "receiver": "Send receiver name",
            "bank": "Send bank code e.g. SCB",
            "last4": "Send last 4 digits",
        }
        await send_card(
            update,
            context,
            cards.edit_card(
                ledger_id=entry_id,
                field=field.upper(),
                current=str(current_map.get(field) or "—"),
                hint=hints.get(field, "Send value"),
            ),
        )
        return


# --- lifecycle -----------------------------------------------------------

def build_app(token: str, db_path: Path | None = None) -> Application:
    application = Application.builder().token(token).build()
    application.bot_data["ledger"] = Ledger(db_path or LEDGER_PATH)

    application.add_handler(CommandHandler(["start", "help"], cmd_start))
    application.add_handler(CommandHandler("rates", cmd_rates))
    application.add_handler(CommandHandler("setrates", cmd_setrates))
    application.add_handler(CommandHandler("balance", cmd_balance))
    application.add_handler(CommandHandler("history", cmd_history))
    application.add_handler(CommandHandler("ledger", cmd_ledger))
    application.add_handler(CommandHandler("demo", cmd_demo))
    application.add_handler(CommandHandler("delete", cmd_delete))
    application.add_handler(CallbackQueryHandler(on_callback))
    application.add_handler(MessageHandler(filters.PHOTO, on_photo))
    application.add_handler(MessageHandler(filters.Document.IMAGE, on_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return application


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN must be set")
    app = build_app(token)
    logger.info("CE VAULT console starting")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
