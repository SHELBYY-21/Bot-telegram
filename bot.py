"""CE VAULT — Premium FinTech Operations Console for Telegram.

Design language: OLED dark terminal. One card per screen. One decision.
Staff inputs: slip image OR USDT/THB amount. Rates are automatic.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import re
from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from cursor_api import CursorAPIError, CursorClient
from vault import cards
from vault.console import (
    active_ledger,
    delete_keyboard,
    edit_keyboard,
    edit_mode,
    remember_ledger,
    send_card,
    set_edit_mode,
    settle_keyboard,
    tx_keyboard,
    typing,
)
from vault.ledger import Ledger
from vault.models import OCRResult, Transaction, TxStatus, utcnow
from vault.ocr import process_slip
from vault.rates import load_rates, profit_pct, quote, save_rates

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO
)
logger = logging.getLogger("cevault")

STATE_FILE = Path(os.environ.get("STATE_FILE", "state.json"))
TERMINAL_STATUSES = {"FINISHED", "COMPLETED", "ERROR", "FAILED", "EXPIRED", "STOPPED", "CANCELLED"}
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "30"))

USDT_ONLY_RE = re.compile(r"^(?:usdt\s*)?(\d+(?:\.\d{1,8})?)\s*(?:usdt)?$", re.I)
THB_ONLY_RE = re.compile(r"^(?:thb\s*)?(\d+(?:,\d{3})*(?:\.\d{1,2})?)\s*(?:thb|บาท)?$", re.I)
EDIT_RE = re.compile(
    r"^(thb|usdt|receiver|bank|last4|buy|sell)\s+(.+)$", re.I
)


# --- persistence (chat settings — backward compatible with state.json) ---

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            logger.warning("state file corrupt, starting fresh")
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def chat_settings(state: dict, chat_id: int) -> dict:
    return state.setdefault(str(chat_id), {})


# --- auth ----------------------------------------------------------------

def allowed_user_ids() -> set[int]:
    raw = os.environ.get("ALLOWED_USER_IDS", "").strip()
    return {int(x) for x in raw.replace(",", " ").split()} if raw else set()


def authorized(update: Update) -> bool:
    allowed = allowed_user_ids()
    if not allowed:
        return True
    return bool(update.effective_user) and update.effective_user.id in allowed


# --- legacy Cursor agent formatting (backward compatibility) -------------

def fmt_agent(agent: dict) -> str:
    lines = [
        f"<b>{html.escape(agent.get('name') or agent.get('id', '?'))}</b>",
        f"id: <code>{html.escape(str(agent.get('id', '?')))}</code>",
        f"status: <b>{html.escape(str(agent.get('status', 'UNKNOWN')))}</b>",
    ]
    source = agent.get("source") or {}
    if source.get("repository"):
        lines.append(f"repo: {html.escape(source['repository'])}")
    target = agent.get("target") or {}
    if target.get("branchName"):
        lines.append(f"branch: <code>{html.escape(target['branchName'])}</code>")
    if target.get("prUrl"):
        lines.append(f"PR: {html.escape(target['prUrl'])}")
    if agent.get("summary"):
        lines.append(f"summary: {html.escape(agent['summary'])}")
    return "\n".join(lines)


async def reply(update: Update, text: str) -> None:
    assert update.effective_message
    await update.effective_message.reply_text(
        text, parse_mode=ParseMode.HTML, disable_web_page_preview=True
    )


def cursor(context: ContextTypes.DEFAULT_TYPE) -> CursorClient:
    return context.application.bot_data["cursor"]


def ledger(context: ContextTypes.DEFAULT_TYPE) -> Ledger:
    return context.application.bot_data["ledger"]


# --- quote helpers -------------------------------------------------------

def apply_quote(tx: Transaction, *, thb: float | None = None, usdt: float | None = None) -> Transaction:
    q = quote(thb=thb, usdt=usdt)
    tx.thb = q["thb"]
    tx.usdt = q["usdt"]
    tx.buy_rate = q["buy_rate"]
    tx.sell_rate = q["sell_rate"]
    tx.profit_pct = q["profit_pct"]
    return tx


def staff_name(update: Update) -> str:
    user = update.effective_user
    if not user:
        return "unknown"
    return user.username or user.full_name or str(user.id)


# --- vault command handlers ----------------------------------------------

HELP = (
    "<b>CE VAULT</b>\n"
    "<i>Secure Ledger</i>\n"
    "────────────────────────\n"
    "Send a slip image\n"
    "or an amount\n\n"
    "<code>500</code> · THB\n"
    "<code>12.5 usdt</code>\n\n"
    "/rates — active spread\n"
    "/balance — inventory\n"
    "/history &lt;last4&gt;\n"
    "/ledger &lt;id&gt;\n"
    "/recent — last entries\n"
    "/setrates &lt;buy&gt; &lt;sell&gt;\n"
    "/setbalance &lt;usdt&gt;\n\n"
    "<i>Rates are automatic. Never enter buy rate on a ticket.</i>"
)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    await send_card(update, context, HELP)


async def cmd_rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    rates = load_rates()
    await send_card(
        update,
        context,
        cards.rates_card(rates["buy_rate"], rates["sell_rate"], profit_pct(rates["buy_rate"], rates["sell_rate"])),
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
        buy, sell = float(context.args[0]), float(context.args[1])
        if buy <= 0 or sell <= 0:
            raise ValueError("rates must be positive")
        save_rates(buy, sell)
    except ValueError:
        await send_card(
            update,
            context,
            cards.error_card(
                problem="Invalid rates",
                cause="Values must be positive numbers",
                action="Use /setrates 39.89 40.00",
            ),
        )
        return
    await cmd_rates(update, context)


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    bal = ledger(context).get_balance()
    await send_card(update, context, cards.balance_card(bal["usdt"], bal["thb"]))


async def cmd_setbalance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not context.args:
        await send_card(
            update,
            context,
            cards.error_card(
                problem="Missing balance",
                cause="USDT inventory value was not provided",
                action="Use /setbalance <usdt>",
            ),
        )
        return
    try:
        usdt = float(context.args[0])
        thb = float(context.args[1]) if len(context.args) > 1 else None
        ledger(context).set_balance(usdt=usdt, thb=thb)
    except ValueError:
        await send_card(
            update,
            context,
            cards.error_card(
                problem="Invalid balance",
                cause="Value must be numeric",
                action="Use /setbalance 50000",
            ),
        )
        return
    await cmd_balance(update, context)


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not context.args:
        await send_card(
            update,
            context,
            cards.error_card(
                problem="Missing receiver",
                cause="No last4 or name provided",
                action="Use /history 3376",
            ),
        )
        return
    key = " ".join(context.args).strip()
    last4 = key if key.isdigit() and len(key) == 4 else None
    hist = ledger(context).receiver_history(
        last4=last4,
        receiver=None if last4 else key,
    )
    if not hist:
        await send_card(
            update,
            context,
            cards.error_card(
                problem="No history",
                cause=f"No settled ledger for {_esc_short(key)}",
                action="Settle a transaction first",
            ),
        )
        return
    await send_card(update, context, cards.history_card(hist))


async def cmd_ledger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not context.args:
        await send_card(
            update,
            context,
            cards.error_card(
                problem="Missing ledger ID",
                cause="No ID provided",
                action="Use /ledger CV-…",
            ),
        )
        return
    tx = ledger(context).get(context.args[0])
    if not tx:
        await send_card(
            update,
            context,
            cards.error_card(
                problem="Ledger not found",
                cause=context.args[0],
                action="Check /recent",
            ),
        )
        return
    remember_ledger(context, tx.ledger_id)
    kb = None
    if tx.status in {TxStatus.OCR_VERIFIED.value, TxStatus.WAITING_USDT.value, TxStatus.RECEIVED.value}:
        kb = tx_keyboard(tx.ledger_id) if tx.thb else None
        text = cards.confirmation_card(tx) if tx.thb else cards.receive_card(tx)
    elif tx.status == TxStatus.SETTLED.value:
        bal = ledger(context).get_balance()
        text = cards.success_card(tx, balance_usdt=bal["usdt"])
    else:
        text = cards.transaction_card(tx)
    await send_card(update, context, text, keyboard=kb)


async def cmd_recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    rows = ledger(context).recent(8)
    if not rows:
        await send_card(
            update,
            context,
            cards.error_card(
                problem="Empty ledger",
                cause="No transactions recorded",
                action="Send a slip or amount",
            ),
        )
        return
    from vault.design import RULE, header, money, mono

    body = [header(), RULE]
    for tx in rows:
        amt = money(tx.thb) if tx.thb is not None else "—"
        body.append(
            f"{mono(tx.ledger_id)}\n"
            f"{html.escape(tx.status)}\n"
            f"{mono(amt)} THB"
        )
        body.append(RULE)
    await send_card(update, context, "\n".join(body).rstrip("─\n"))

def _esc_short(value: str) -> str:
    return html.escape(value[:40])


# --- inbound slip / amount -----------------------------------------------

async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    assert update.effective_message and update.effective_user
    await typing(update, context)

    photo = update.effective_message.photo[-1]
    caption = update.effective_message.caption or ""
    tx = Transaction.create(
        staff=staff_name(update),
        staff_id=update.effective_user.id,
        chat_id=update.effective_chat.id if update.effective_chat else None,
    )
    tx.slip_file_id = photo.file_id
    tx.status = TxStatus.RECEIVED.value
    ledger(context).upsert(tx)
    remember_ledger(context, tx.ledger_id)

    msg = await send_card(
        update,
        context,
        cards.loading_card(tx.ledger_id, phase="RECEIVED · Vision"),
    )
    tx.message_id = msg.message_id
    ledger(context).upsert(tx)

    # Download + OCR
    image_bytes = None
    try:
        tg_file = await context.bot.get_file(photo.file_id)
        buf = await tg_file.download_as_bytearray()
        image_bytes = bytes(buf)
    except Exception as e:
        logger.warning("slip download failed: %s", e)

    ocr, digest = await process_slip(
        image_bytes=image_bytes,
        caption=caption,
        file_id=photo.file_id,
    )
    await _finalize_ocr(update, context, tx, ocr, digest)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    assert update.effective_message and update.effective_user
    text = (update.effective_message.text or "").strip()
    if not text or text.startswith("/"):
        return

    # Edit mode corrections
    edit_id = edit_mode(context)
    if edit_id:
        await _apply_edit(update, context, edit_id, text)
        return

    # Structured slip paste (multi-line) → OCR path
    if "\n" in text or re.search(r"(receiver|bank|last4|นาย|scb|kbank)", text, re.I):
        await typing(update, context)
        tx = Transaction.create(
            staff=staff_name(update),
            staff_id=update.effective_user.id,
            chat_id=update.effective_chat.id if update.effective_chat else None,
        )
        tx.status = TxStatus.RECEIVED.value
        ledger(context).upsert(tx)
        remember_ledger(context, tx.ledger_id)
        msg = await send_card(update, context, cards.loading_card(tx.ledger_id, phase="Parsing"))
        tx.message_id = msg.message_id
        ocr, digest = await process_slip(caption=text, file_id=f"text:{digest_seed(text)}")
        await _finalize_ocr(update, context, tx, ocr, digest)
        return

    usdt_m = USDT_ONLY_RE.match(text)
    thb_m = THB_ONLY_RE.match(text)
    # Prefer USDT when user explicitly marks it
    if re.search(r"usdt", text, re.I) and usdt_m:
        await _quote_from_amount(update, context, usdt=float(usdt_m.group(1)))
        return
    if thb_m and not re.search(r"usdt", text, re.I):
        raw = thb_m.group(1).replace(",", "")
        await _quote_from_amount(update, context, thb=float(raw))
        return
    if usdt_m:
        await _quote_from_amount(update, context, usdt=float(usdt_m.group(1)))
        return

    await send_card(
        update,
        context,
        cards.error_card(
            problem="Unrecognized input",
            cause="Expected slip image or amount",
            action="Send 500 or 12.5 usdt",
        ),
    )


def digest_seed(text: str) -> str:
    return text[:200]


async def _quote_from_amount(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    thb: float | None = None,
    usdt: float | None = None,
) -> None:
    assert update.effective_user
    await typing(update, context)
    tx = Transaction.create(
        staff=staff_name(update),
        staff_id=update.effective_user.id,
        chat_id=update.effective_chat.id if update.effective_chat else None,
    )
    apply_quote(tx, thb=thb, usdt=usdt)
    tx.status = TxStatus.WAITING_USDT.value
    ledger(context).upsert(tx)
    remember_ledger(context, tx.ledger_id)
    msg = await send_card(
        update,
        context,
        cards.confirmation_card(tx),
        keyboard=tx_keyboard(tx.ledger_id),
    )
    tx.message_id = msg.message_id
    ledger(context).upsert(tx)


async def _finalize_ocr(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    tx: Transaction,
    ocr: OCRResult,
    digest: str,
) -> None:
    store = ledger(context)

    # Duplicate slip detection
    prior = store.find_by_slip_hash(digest)
    if prior and prior.ledger_id != tx.ledger_id:
        ocr.duplicate_slip = True

    if ocr.last4 or ocr.receiver:
        ocr.repeated_receiver = store.has_receiver(last4=ocr.last4, receiver=ocr.receiver)

    tx.slip_hash = digest
    tx.receiver = ocr.receiver
    tx.bank = ocr.bank
    tx.last4 = ocr.last4
    tx.ocr_confidence = ocr.confidence
    tx.ocr = ocr.to_dict()
    tx.status = TxStatus.OCR_VERIFIED.value if ocr.confidence >= 50 else TxStatus.ERROR.value

    if ocr.duplicate_slip:
        store.upsert(tx)
        await send_card(
            update,
            context,
            cards.error_card(
                problem="Duplicate slip",
                cause=f"Matches {prior.ledger_id if prior else 'prior entry'}",
                action="Cancel or verify manually",
                ledger_id=tx.ledger_id,
            ),
            keyboard=tx_keyboard(tx.ledger_id),
            edit_message_id=tx.message_id,
        )
        return

    if ocr.amount_thb is not None:
        apply_quote(tx, thb=ocr.amount_thb)

    store.upsert(tx)

    # Show OCR card briefly, then transition to confirmation (edit in place)
    await send_card(
        update,
        context,
        cards.ocr_card(tx, ocr),
        edit_message_id=tx.message_id,
    )
    await asyncio.sleep(0.8)

    if tx.thb is None:
        await send_card(
            update,
            context,
            cards.error_card(
                problem="Amount not detected",
                cause=f"Vision {ocr.confidence:.1f}%",
                action="Send amount as 500 or edit",
                ledger_id=tx.ledger_id,
            ),
            keyboard=edit_keyboard(tx.ledger_id),
            edit_message_id=tx.message_id,
        )
        set_edit_mode(context, tx.ledger_id)
        return

    if ocr.below_threshold:
        # Still allow confirm, but status stays review-oriented
        pass

    tx.status = TxStatus.WAITING_USDT.value
    store.upsert(tx)
    await send_card(
        update,
        context,
        cards.confirmation_card(tx),
        keyboard=tx_keyboard(tx.ledger_id),
        edit_message_id=tx.message_id,
    )


async def _apply_edit(
    update: Update, context: ContextTypes.DEFAULT_TYPE, ledger_id: str, text: str
) -> None:
    store = ledger(context)
    tx = store.get(ledger_id)
    if not tx:
        set_edit_mode(context, None)
        await send_card(
            update,
            context,
            cards.error_card(
                problem="Ledger not found",
                cause=ledger_id,
                action="Start a new ticket",
            ),
        )
        return

    m = EDIT_RE.match(text.strip())
    if not m:
        await send_card(
            update,
            context,
            cards.edit_card(tx),
            keyboard=edit_keyboard(tx.ledger_id),
        )
        return

    field, raw = m.group(1).lower(), m.group(2).strip()
    try:
        if field == "thb":
            apply_quote(tx, thb=float(raw.replace(",", "")))
        elif field == "usdt":
            apply_quote(tx, usdt=float(raw))
        elif field == "receiver":
            tx.receiver = raw
        elif field == "bank":
            tx.bank = raw.upper()
        elif field == "last4":
            tx.last4 = "".join(c for c in raw if c.isdigit())[-4:]
        elif field == "buy":
            tx.buy_rate = float(raw)
            if tx.sell_rate is not None:
                tx.profit_pct = profit_pct(tx.buy_rate, tx.sell_rate)
        elif field == "sell":
            rates = load_rates()
            buy = tx.buy_rate if tx.buy_rate is not None else rates["buy_rate"]
            if tx.thb is not None:
                q = quote(thb=tx.thb, sell_rate=float(raw), buy_rate=buy)
            elif tx.usdt is not None:
                q = quote(usdt=tx.usdt, sell_rate=float(raw), buy_rate=buy)
            else:
                tx.sell_rate = float(raw)
                tx.profit_pct = profit_pct(buy, tx.sell_rate)
                q = None
            if q:
                tx.thb, tx.usdt = q["thb"], q["usdt"]
                tx.buy_rate, tx.sell_rate, tx.profit_pct = (
                    q["buy_rate"],
                    q["sell_rate"],
                    q["profit_pct"],
                )
    except ValueError:
        await send_card(
            update,
            context,
            cards.error_card(
                problem="Invalid edit",
                cause=text,
                action="Example: thb 500",
                ledger_id=tx.ledger_id,
            ),
            keyboard=edit_keyboard(tx.ledger_id),
        )
        return

    if tx.status == TxStatus.RECEIVED.value:
        tx.status = TxStatus.WAITING_USDT.value
    store.upsert(tx)
    set_edit_mode(context, None)
    await send_card(
        update,
        context,
        cards.confirmation_card(tx),
        keyboard=tx_keyboard(tx.ledger_id),
    )


# --- callback actions ----------------------------------------------------

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    query = update.callback_query
    assert query and query.data
    await query.answer()
    parts = query.data.split(":", 2)
    if len(parts) != 3 or parts[0] != "tx":
        return
    action, ledger_id = parts[1], parts[2]
    store = ledger(context)
    tx = store.get(ledger_id)
    if not tx:
        await send_card(
            update,
            context,
            cards.error_card(
                problem="Ledger not found",
                cause=ledger_id,
                action="Start a new ticket",
            ),
        )
        return

    if action == "confirm":
        tx.status = TxStatus.WAITING_USDT.value
        store.upsert(tx)
        await send_card(
            update,
            context,
            cards.transaction_card(tx)
            + "\n────────────────────────\nAwaiting USDT transfer",
            keyboard=settle_keyboard(tx.ledger_id),
        )
        return

    if action == "settle":
        tx.status = TxStatus.SETTLED.value
        tx.settled_at = utcnow()
        store.upsert(tx)
        bal = store.apply_settlement(tx)
        set_edit_mode(context, None)
        await send_card(
            update,
            context,
            cards.success_card(tx, balance_usdt=bal["usdt"]),
        )
        return

    if action == "edit":
        set_edit_mode(context, tx.ledger_id)
        await send_card(
            update,
            context,
            cards.edit_card(tx),
            keyboard=edit_keyboard(tx.ledger_id),
        )
        return

    if action == "back":
        set_edit_mode(context, None)
        await send_card(
            update,
            context,
            cards.confirmation_card(tx),
            keyboard=tx_keyboard(tx.ledger_id),
        )
        return

    if action == "cancel":
        set_edit_mode(context, None)
        await send_card(
            update,
            context,
            cards.delete_card(tx),
            keyboard=delete_keyboard(tx.ledger_id),
        )
        return

    if action == "delete":
        store.delete(tx.ledger_id)
        set_edit_mode(context, None)
        if active_ledger(context) == tx.ledger_id:
            context.chat_data.pop("active_ledger", None)
        await send_card(
            update,
            context,
            cards.error_card(
                problem="Deleted",
                cause=tx.ledger_id,
                action="Ledger entry removed",
                ledger_id=tx.ledger_id,
            ),
        )
        return


# --- Cursor agent polling (backward compatible) --------------------------

async def poll_agent(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    assert job and job.data
    agent_id: str = job.data["agent_id"]
    chat_id: int = job.data["chat_id"]
    try:
        agent = await cursor(context).get_agent(agent_id)
    except CursorAPIError as e:
        logger.warning("poll failed for %s: %s", agent_id, e)
        if e.status_code == 404:
            job.schedule_removal()
        return
    status = str(agent.get("status", "")).upper()
    last = job.data.get("last_status")
    if status != last:
        job.data["last_status"] = status
        await context.bot.send_message(
            chat_id,
            fmt_agent(agent),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    if status in TERMINAL_STATUSES:
        job.schedule_removal()


def watch_agent(context: ContextTypes.DEFAULT_TYPE, chat_id: int, agent: dict) -> None:
    if not context.job_queue:
        return
    name = f"poll:{agent['id']}"
    if context.job_queue.get_jobs_by_name(name):
        return
    context.job_queue.run_repeating(
        poll_agent,
        interval=POLL_INTERVAL,
        first=POLL_INTERVAL,
        name=name,
        data={
            "agent_id": agent["id"],
            "chat_id": chat_id,
            "last_status": str(agent.get("status", "")).upper(),
        },
    )


async def cmd_repo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not context.args:
        await reply(update, "Usage: /repo &lt;github-url&gt; [ref]")
        return
    if "cursor" not in context.application.bot_data or context.application.bot_data.get("cursor") is None:
        await reply(update, "Cursor API not configured.")
        return
    state = context.application.bot_data["state"]
    settings = chat_settings(state, update.effective_chat.id)
    settings["repository"] = context.args[0]
    settings["ref"] = context.args[1] if len(context.args) > 1 else None
    save_state(state)
    ref = settings["ref"] or "default branch"
    await reply(update, f"Repository set to {html.escape(settings['repository'])} ({html.escape(ref)})")


async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not context.args:
        await reply(update, "Usage: /model &lt;model-name&gt;")
        return
    state = context.application.bot_data["state"]
    settings = chat_settings(state, update.effective_chat.id)
    settings["model"] = context.args[0]
    save_state(state)
    await reply(update, f"Model set to <code>{html.escape(settings['model'])}</code>")


async def cmd_models(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not _cursor_ready(context):
        await reply(update, "Cursor API not configured.")
        return
    try:
        data = await cursor(context).list_models()
    except CursorAPIError as e:
        await reply(update, html.escape(str(e)))
        return
    models = data.get("models", data if isinstance(data, list) else [])
    if not models:
        await reply(update, "No models returned.")
        return
    await reply(update, "\n".join(f"• <code>{html.escape(str(m))}</code>" for m in models))


async def cmd_repos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not _cursor_ready(context):
        await reply(update, "Cursor API not configured.")
        return
    try:
        data = await cursor(context).list_repositories()
    except CursorAPIError as e:
        await reply(update, html.escape(str(e)))
        return
    repos = data.get("repositories", [])
    if not repos:
        await reply(update, "No repositories returned.")
        return
    lines = []
    for r in repos[:50]:
        if isinstance(r, dict):
            lines.append(f"• {html.escape(r.get('repository') or r.get('url') or str(r))}")
        else:
            lines.append(f"• {html.escape(str(r))}")
    await reply(update, "\n".join(lines))


async def cmd_agent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not _cursor_ready(context):
        await reply(update, "Cursor API not configured.")
        return
    prompt = " ".join(context.args or [])
    if not prompt:
        await reply(update, "Usage: /agent &lt;prompt&gt;")
        return
    state = context.application.bot_data["state"]
    settings = chat_settings(state, update.effective_chat.id)
    repository = settings.get("repository") or os.environ.get("DEFAULT_REPOSITORY")
    if not repository:
        await reply(update, "No repository configured. Set one with /repo &lt;url&gt; first.")
        return
    try:
        agent = await cursor(context).create_agent(
            prompt_text=prompt,
            repository=repository,
            ref=settings.get("ref"),
            model=settings.get("model") or os.environ.get("DEFAULT_MODEL"),
            auto_create_pr=os.environ.get("AUTO_CREATE_PR", "").lower() in ("1", "true", "yes"),
        )
    except CursorAPIError as e:
        await reply(update, f"Failed to launch agent: {html.escape(str(e))}")
        return
    watch_agent(context, update.effective_chat.id, agent)
    await reply(update, "Agent launched\n" + fmt_agent(agent))


async def cmd_agents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not _cursor_ready(context):
        await reply(update, "Cursor API not configured.")
        return
    try:
        data = await cursor(context).list_agents(limit=10)
    except CursorAPIError as e:
        await reply(update, html.escape(str(e)))
        return
    agents = data.get("agents", [])
    if not agents:
        await reply(update, "No agents found.")
        return
    await reply(update, "\n\n".join(fmt_agent(a) for a in agents))


async def _require_id(update: Update, context: ContextTypes.DEFAULT_TYPE, usage: str) -> str | None:
    if not context.args:
        await reply(update, usage)
        return None
    return context.args[0]


def _cursor_ready(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return context.application.bot_data.get("cursor") is not None


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not _cursor_ready(context):
        await reply(update, "Cursor API not configured.")
        return
    agent_id = await _require_id(update, context, "Usage: /status &lt;agent-id&gt;")
    if not agent_id:
        return
    try:
        agent = await cursor(context).get_agent(agent_id)
    except CursorAPIError as e:
        await reply(update, html.escape(str(e)))
        return
    await reply(update, fmt_agent(agent))


async def cmd_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not _cursor_ready(context):
        await reply(update, "Cursor API not configured.")
        return
    agent_id = await _require_id(update, context, "Usage: /conversation &lt;agent-id&gt;")
    if not agent_id:
        return
    try:
        data = await cursor(context).get_conversation(agent_id)
    except CursorAPIError as e:
        await reply(update, html.escape(str(e)))
        return
    messages = data.get("messages", [])
    if not messages:
        await reply(update, "No messages in this conversation.")
        return
    lines = []
    for m in messages:
        role = m.get("type") or m.get("role") or "message"
        text = m.get("text") or ""
        lines.append(f"<b>{html.escape(str(role))}</b>: {html.escape(text)}")
    out = "\n\n".join(lines)
    if len(out) > 3900:
        out = "…" + out[-3900:]
    await reply(update, out)


async def cmd_followup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not _cursor_ready(context):
        await reply(update, "Cursor API not configured.")
        return
    if not context.args or len(context.args) < 2:
        await reply(update, "Usage: /followup &lt;agent-id&gt; &lt;instructions&gt;")
        return
    agent_id, text = context.args[0], " ".join(context.args[1:])
    try:
        await cursor(context).add_followup(agent_id, text)
    except CursorAPIError as e:
        await reply(update, html.escape(str(e)))
        return
    watch_agent(context, update.effective_chat.id, {"id": agent_id, "status": "RUNNING"})
    await reply(update, f"Follow-up sent to <code>{html.escape(agent_id)}</code>")


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not _cursor_ready(context):
        await reply(update, "Cursor API not configured.")
        return
    agent_id = await _require_id(update, context, "Usage: /stop &lt;agent-id&gt;")
    if not agent_id:
        return
    try:
        await cursor(context).stop_agent(agent_id)
    except CursorAPIError as e:
        await reply(update, html.escape(str(e)))
        return
    await reply(update, f"Stopped <code>{html.escape(agent_id)}</code>")


async def cmd_delete_agent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not _cursor_ready(context):
        await reply(update, "Cursor API not configured.")
        return
    agent_id = await _require_id(update, context, "Usage: /delete &lt;agent-id&gt;")
    if not agent_id:
        return
    try:
        await cursor(context).delete_agent(agent_id)
    except CursorAPIError as e:
        await reply(update, html.escape(str(e)))
        return
    await reply(update, f"Deleted <code>{html.escape(agent_id)}</code>")


async def cmd_me(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not _cursor_ready(context):
        await reply(update, "Cursor API not configured.")
        return
    try:
        info = await cursor(context).me()
    except CursorAPIError as e:
        await reply(update, html.escape(str(e)))
        return
    await reply(update, f"<pre>{html.escape(json.dumps(info, indent=2))}</pre>")


# --- app lifecycle -------------------------------------------------------

async def on_shutdown(application: Application) -> None:
    client = application.bot_data.get("cursor")
    if client is not None:
        await client.close()


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN must be set")

    application = Application.builder().token(token).post_shutdown(on_shutdown).build()
    application.bot_data["ledger"] = Ledger()
    application.bot_data["state"] = load_state()

    api_key = os.environ.get("CURSOR_API_KEY", "").strip()
    application.bot_data["cursor"] = CursorClient(api_key) if api_key else None

    vault_handlers = {
        "start": cmd_start,
        "help": cmd_start,
        "rates": cmd_rates,
        "setrates": cmd_setrates,
        "balance": cmd_balance,
        "setbalance": cmd_setbalance,
        "history": cmd_history,
        "ledger": cmd_ledger,
        "recent": cmd_recent,
    }
    for name, fn in vault_handlers.items():
        application.add_handler(CommandHandler(name, fn))

    # Legacy Cursor Cloud Agents commands (optional; requires CURSOR_API_KEY)
    legacy = {
        "repo": cmd_repo,
        "model": cmd_model,
        "models": cmd_models,
        "repos": cmd_repos,
        "agent": cmd_agent,
        "agents": cmd_agents,
        "status": cmd_status,
        "conversation": cmd_conversation,
        "followup": cmd_followup,
        "stop": cmd_stop,
        "delete": cmd_delete_agent,
        "me": cmd_me,
    }
    for name, fn in legacy.items():
        application.add_handler(CommandHandler(name, fn))

    application.add_handler(CallbackQueryHandler(on_callback))
    application.add_handler(MessageHandler(filters.PHOTO, on_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    logger.info("CE VAULT console starting")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
