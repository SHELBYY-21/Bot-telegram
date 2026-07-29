"""Telegram handlers — CE VAULT card UX on LedgerStore (SQLite | Supabase)."""

from __future__ import annotations

import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

from ce_vault import cards, keyboards
from ce_vault.console import answer_callback, render, show_typing
from ce_vault.ocr import (
    DEMO_SLIP_TEXT,
    analyze_slip,
    parse_edit_command,
    parse_usdt_amount,
)
from ce_vault.rates import RateQuote, compute_from_thb, compute_from_usdt
from ce_vault.store import LedgerStore
from ce_vault.theme import Status

logger = logging.getLogger("ce_vault.handlers")


def _ledger(context: ContextTypes.DEFAULT_TYPE) -> LedgerStore:
    return context.application.bot_data["ledger"]


def _sessions(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["sessions"]


def _settings(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["settings"]


def _quote(context: ContextTypes.DEFAULT_TYPE) -> RateQuote:
    buy, sell = _ledger(context).get_rates()
    return RateQuote(buy_rate=buy, sell_rate=sell)


def allowed_user_ids(store: LedgerStore | None = None) -> set[int]:
    raw = os.environ.get("ALLOWED_USER_IDS", "").strip()
    if raw:
        return {int(x) for x in raw.replace(",", " ").split() if x}
    if store is not None and hasattr(store, "list_admin_telegram_ids"):
        try:
            return set(store.list_admin_telegram_ids())  # type: ignore[attr-defined]
        except Exception as exc:
            logger.warning("could not load admin allowlist: %s", exc)
    return set()


def authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    settings = _settings(context)
    if settings.allowed_user_ids:
        user = update.effective_user
        return bool(user) and user.id in settings.allowed_user_ids
    allowed = allowed_user_ids(_ledger(context))
    if not allowed:
        return True
    user = update.effective_user
    return bool(user) and user.id in allowed


def _entry_status(entry: dict) -> str:
    return entry.get("status") or Status.RECEIVED.value


# --- home / rates --------------------------------------------------------

async def show_home(
    update: Update, context: ContextTypes.DEFAULT_TYPE, *, reset: bool = False
) -> None:
    chat_id = update.effective_chat.id
    if reset:
        _sessions(context).update(
            chat_id, active_ledger_id=None, mode="idle", draft={}
        )
        if hasattr(context, "user_data"):
            context.user_data.pop("edit_field", None)
            context.user_data.pop("active_ledger_id", None)
    q = _quote(context)
    bal = _ledger(context).get_balance()
    text = cards.console_home(
        buy_rate=q.buy_rate,
        sell_rate=q.sell_rate,
        balance_usdt=bal,
    )
    await render(update, context, text, prefer_edit=True)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    await show_home(update, context, reset=True)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    await show_home(update, context)


async def cmd_rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    await show_home(update, context)


async def cmd_setrates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    args = context.args or []
    if len(args) < 2:
        await render(
            update,
            context,
            cards.error_card(
                problem="Rates required",
                cause="Desk publish needs buy and sell.",
                action="Example: /setrates 39.89 40.00",
            ),
        )
        return
    try:
        buy, sell = float(args[0]), float(args[1])
        if buy <= 0 or sell <= 0:
            raise ValueError("non-positive")
    except ValueError:
        await render(
            update,
            context,
            cards.error_card(
                problem="Invalid rates",
                cause="Buy and sell must be positive numbers.",
                action="Example: /setrates 39.89 40.00",
            ),
        )
        return
    staff = update.effective_user
    _ledger(context).set_rates(buy, sell, updated_by=staff.id if staff else None)
    await show_home(update, context)


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    args = context.args or []
    store = _ledger(context)
    if args:
        try:
            value = float(args[0])
        except ValueError:
            await render(
                update,
                context,
                cards.error_card(
                    problem="Invalid balance",
                    cause="USDT float must be a number.",
                    action="Use /balance <usdt>",
                ),
            )
            return
        store.set_balance(value)
    await show_home(update, context)


# --- ledger / history / demo / delete ------------------------------------

async def cmd_ledger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    args = context.args or []
    if args:
        entry = _ledger(context).get(args[0])
        if not entry:
            await render(
                update,
                context,
                cards.error_card(
                    problem="Not found",
                    cause=f"{args[0]} is not in the vault.",
                    action="Check /ledger for recent ids.",
                ),
            )
            return
        await _show_entry_card(update, context, entry)
        return

    entries = _ledger(context).list_recent(8)
    if not entries:
        await render(
            update,
            context,
            cards.error_card(
                problem="Ledger empty",
                cause="No settlements recorded yet.",
                action="Submit a slip or USDT amount to open an entry.",
            ),
        )
        return
    lines = [cards.header(subtitle="Ledger"), ""]
    for e in entries:
        lines.append(cards.compact_ledger_line(e))
        lines.append("")
    await render(update, context, "\n".join(lines).rstrip())


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    args = context.args or []
    bank, last4 = None, None
    if len(args) >= 2:
        bank, last4 = args[0], args[1]
    elif len(args) == 1 and args[0].isdigit() and len(args[0]) == 4:
        last4 = args[0]
    else:
        sess = _sessions(context).get(update.effective_chat.id)
        lid = sess.active_ledger_id or context.user_data.get("active_ledger_id")
        if lid:
            entry = _ledger(context).get(lid)
            if entry:
                bank, last4 = entry.get("bank"), entry.get("last4")
    if not last4:
        await render(
            update,
            context,
            cards.error_card(
                problem="Receiver required",
                cause="History lookup needs bank + last4.",
                action="Usage: /history SCB 3376",
            ),
        )
        return
    hist = _ledger(context).receiver_history(bank or "", last4)
    if not hist:
        await render(
            update,
            context,
            cards.error_card(
                problem="No history",
                cause=f"No ledger trail for {(bank or 'BANK').upper()} ••••{last4[-4:]}",
                action="Settle a transaction first.",
            ),
        )
        return
    await render(
        update,
        context,
        cards.history_card(
            bank=hist.get("bank") or bank or "BANK",
            last4=hist.get("last4") or last4,
            tx_count=int(hist.get("tx_count") or 0),
            total_thb=float(hist.get("total_thb") or 0),
            total_usdt=float(hist.get("total_usdt") or 0),
            first_seen=hist.get("first_seen"),
            last_seen=hist.get("last_seen"),
            receiver_name=hist.get("name") or hist.get("receiver_name"),
        ),
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    ledger_id = (context.args or [None])[0]
    if not ledger_id:
        sess = _sessions(context).get(update.effective_chat.id)
        ledger_id = sess.active_ledger_id or context.user_data.get("active_ledger_id")
    if not ledger_id:
        await render(
            update,
            context,
            cards.error_card(
                problem="No active ledger",
                cause="Status requires a ledger id.",
                action="Usage: /status LV-…",
            ),
        )
        return
    entry = _ledger(context).get(ledger_id)
    if not entry:
        await render(
            update,
            context,
            cards.error_card(
                problem="Not found",
                cause=f"{ledger_id} is not in the vault.",
                action="Check /ledger for recent ids.",
            ),
        )
        return
    await _show_entry_card(update, context, entry)


async def cmd_demo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    await begin_from_ocr(
        update, context, text=DEMO_SLIP_TEXT, file_unique_id="demo-slip-v1"
    )


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    ledger_id = (context.args or [None])[0]
    if not ledger_id:
        await render(
            update,
            context,
            cards.error_card(
                problem="Ledger id required",
                cause="Delete needs an explicit target.",
                action="Usage: /delete LV-…",
            ),
        )
        return
    entry = _ledger(context).get(ledger_id)
    if not entry:
        await render(
            update,
            context,
            cards.error_card(
                problem="Not found",
                cause=f"{ledger_id} does not exist.",
                action="Nothing deleted.",
            ),
        )
        return
    await render(
        update,
        context,
        cards.delete_card(
            ledger_id=entry["id"],
            thb=entry.get("thb"),
            bank=entry.get("bank"),
            last4=entry.get("last4"),
        ),
        keyboard=keyboards.delete_keyboard(entry["id"]),
    )


# --- intake --------------------------------------------------------------

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

    await show_typing(update, context)
    await render(update, context, cards.loading_card(phase="Vision"), prefer_edit=True)

    result, digest = await analyze_slip(
        text=text, image_bytes=image_bytes, file_unique_id=file_unique_id
    )
    settings = _settings(context)
    warn = result.confidence < settings.ocr_warn_below

    store = _ledger(context)
    duplicate = store.find_by_slip_hash(digest)
    repeat = store.is_repeat_receiver(result.bank, result.last4)
    repeat_count = 0
    hist = store.receiver_history(result.bank, result.last4)
    if hist:
        repeat_count = int(hist.get("tx_count") or 0)

    if image_bytes:
        settings.images_dir.mkdir(parents=True, exist_ok=True)

    q = _quote(context)
    amounts = (
        compute_from_thb(result.amount_thb, q)
        if result.amount_thb
        else {
            "thb": None,
            "usdt": None,
            "buy_rate": q.buy_rate,
            "sell_rate": q.sell_rate,
            "profit_pct": round(q.profit_pct, 2),
        }
    )

    status = (
        Status.OCR_VERIFIED.value
        if result.amount_thb and not warn
        else Status.RECEIVED.value
    )
    entry = store.create_entry(
        status=status,
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
        notes="duplicate_slip" if duplicate else None,
    )
    _sessions(context).update(
        update.effective_chat.id, active_ledger_id=entry["id"], mode="idle"
    )
    context.user_data["active_ledger_id"] = entry["id"]

    await render(
        update,
        context,
        cards.ocr_card(
            ledger_id=entry["id"],
            confidence=result.confidence,
            receiver_name=result.receiver_name,
            bank=result.bank,
            last4=result.last4,
            amount=result.amount_thb,
            verified=bool(result.amount_thb and result.bank and result.last4 and not warn),
            warn=warn,
            duplicate=bool(duplicate),
            repeat_receiver=repeat or repeat_count > 0,
            repeat_count=repeat_count,
        ),
        keyboard=keyboards.ocr_keyboard(entry["id"], warn=warn or bool(duplicate)),
    )


async def begin_from_usdt(
    update: Update, context: ContextTypes.DEFAULT_TYPE, usdt_amount: float
) -> None:
    user = update.effective_user
    assert user and update.effective_chat
    await show_typing(update, context)
    await render(update, context, cards.loading_card(phase="Quote"), prefer_edit=True)

    q = _quote(context)
    amounts = compute_from_usdt(usdt_amount, q)
    entry = _ledger(context).create_entry(
        status=Status.WAITING_USDT.value,
        thb=amounts["thb"],
        usdt=amounts["usdt"],
        buy_rate=amounts["buy_rate"],
        sell_rate=amounts["sell_rate"],
        profit_pct=amounts["profit_pct"],
        staff_id=user.id,
        staff_name=user.full_name,
        chat_id=update.effective_chat.id,
    )
    _sessions(context).update(
        update.effective_chat.id, active_ledger_id=entry["id"], mode="idle"
    )
    context.user_data["active_ledger_id"] = entry["id"]
    await _show_confirmation(update, context, entry)


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    assert update.effective_message and update.effective_message.photo
    photo = update.effective_message.photo[-1]
    tg_file = await context.bot.get_file(photo.file_id)
    image_bytes = bytes(await tg_file.download_as_bytearray())
    caption = update.effective_message.caption or None
    await begin_from_ocr(
        update,
        context,
        text=caption,
        image_bytes=image_bytes,
        file_id=photo.file_id,
        file_unique_id=photo.file_unique_id,
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    assert update.effective_message and update.effective_message.text
    text = update.effective_message.text.strip()
    if text.startswith("/"):
        return

    chat_id = update.effective_chat.id
    sess = _sessions(context).get(chat_id)

    if sess.mode == "edit" and sess.active_ledger_id:
        await _apply_edit(update, context, sess.active_ledger_id, text)
        return

    if any(
        k in text.lower()
        for k in ("thb", "บาท", "bank", "scb", "kbank", "นาย", "นาง", "ผู้รับ")
    ):
        await begin_from_ocr(update, context, text=text)
        return

    usdt = parse_usdt_amount(text)
    if usdt is not None:
        await begin_from_usdt(update, context, usdt)
        return

    await render(
        update,
        context,
        cards.error_card(
            problem="Unrecognized input",
            cause="Console expects a slip image or a USDT amount.",
            action="Example: 12.5   or   USDT 12.5   or   /demo",
        ),
    )


async def _apply_edit(
    update: Update, context: ContextTypes.DEFAULT_TYPE, ledger_id: str, text: str
) -> None:
    patch = parse_edit_command(text)
    if not patch:
        await render(
            update,
            context,
            cards.error_card(
                problem="Invalid edit",
                cause="Could not parse correction.",
                action="THB 500  ·  USDT 12.5  ·  BANK SCB 3376",
            ),
        )
        return
    store = _ledger(context)
    entry = store.get(ledger_id)
    if not entry:
        await render(
            update,
            context,
            cards.error_card(
                problem="Not found",
                cause="Ledger entry disappeared.",
                action="Open a new entry.",
            ),
        )
        return

    fields: dict = {}
    if "bank" in patch:
        fields["bank"] = patch["bank"]
    if "last4" in patch:
        fields["last4"] = patch["last4"]

    q = _quote(context)
    if "usdt" in patch:
        fields.update(compute_from_usdt(patch["usdt"], q))
    elif "thb" in patch:
        fields.update(compute_from_thb(patch["thb"], q))

    entry = store.update(ledger_id, **fields)
    _sessions(context).update(update.effective_chat.id, mode="idle")
    assert entry
    await _show_confirmation(update, context, entry)


# --- cards ---------------------------------------------------------------

async def _show_confirmation(
    update: Update, context: ContextTypes.DEFAULT_TYPE, entry: dict
) -> None:
    q = _quote(context)
    status = _entry_status(entry)
    if entry.get("thb") is None or entry.get("usdt") is None:
        await render(
            update,
            context,
            cards.receive_card(
                ledger_id=entry["id"],
                thb=entry.get("thb"),
                usdt=entry.get("usdt"),
                buy_rate=entry.get("buy_rate") or q.buy_rate,
                sell_rate=entry.get("sell_rate") or q.sell_rate,
                bank=entry.get("bank"),
                last4=entry.get("last4"),
                status=status,
                hint="Awaiting amount",
            ),
            keyboard=keyboards.confirm_keyboard(entry["id"]),
        )
        return

    # After confirm → waiting USDT uses settle keyboard
    keyboard = (
        keyboards.settle_keyboard(entry["id"])
        if status == Status.WAITING_USDT.value
        else keyboards.confirm_keyboard(entry["id"])
    )
    await render(
        update,
        context,
        cards.confirmation_card(
            ledger_id=entry["id"],
            thb=float(entry["thb"]),
            usdt=float(entry["usdt"]),
            buy_rate=float(entry.get("buy_rate") or q.buy_rate),
            sell_rate=float(entry.get("sell_rate") or q.sell_rate),
            profit_pct=float(entry.get("profit_pct") or 0),
            bank=entry.get("bank"),
            last4=entry.get("last4"),
            confidence=entry.get("ocr_confidence"),
            status=status
            if status != Status.RECEIVED.value
            else Status.OCR_VERIFIED.value,
        ),
        keyboard=keyboard,
    )


async def _show_entry_card(
    update: Update, context: ContextTypes.DEFAULT_TYPE, entry: dict
) -> None:
    if _entry_status(entry) == Status.SETTLED.value:
        bal = _ledger(context).get_balance()
        await render(
            update,
            context,
            cards.success_card(
                ledger_id=entry["id"],
                profit_pct=entry.get("profit_pct"),
                profit_thb=None,
                balance_thb=None,
                balance_usdt=bal,
            ),
            keyboard=keyboards.done_keyboard(),
        )
        return
    await _show_confirmation(update, context, entry)


# --- callbacks -----------------------------------------------------------

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    query = update.callback_query
    assert query and query.data
    data = query.data

    if data == "home":
        await answer_callback(update)
        await show_home(update, context, reset=True)
        return

    if ":" not in data:
        await answer_callback(update)
        return

    action, ledger_id = data.split(":", 1)
    # Support legacy tx:action:id from older main branch keyboards if any
    if action == "tx" and ":" in ledger_id:
        action, ledger_id = ledger_id.split(":", 1)

    store = _ledger(context)
    entry = store.get(ledger_id)

    if action == "ocr_ok":
        await answer_callback(update, "Quoted")
        if not entry:
            await render(
                update,
                context,
                cards.error_card(
                    problem="Not found",
                    cause="OCR session expired.",
                    action="Resubmit the slip.",
                ),
            )
            return
        q = _quote(context)
        fields: dict = {"status": Status.OCR_VERIFIED.value}
        if entry.get("thb") is not None and entry.get("usdt") is None:
            fields.update(compute_from_thb(float(entry["thb"]), q))
        elif entry.get("thb") is None and entry.get("usdt") is not None:
            fields.update(compute_from_usdt(float(entry["usdt"]), q))
        entry = store.update(ledger_id, **fields)
        assert entry
        await _show_confirmation(update, context, entry)
        return

    if action == "confirm":
        await answer_callback(update, "Waiting USDT")
        if not entry:
            await render(
                update,
                context,
                cards.error_card(
                    problem="Not found",
                    cause="Nothing to confirm.",
                    action="Open a new entry.",
                ),
            )
            return
        if entry.get("thb") is None or entry.get("usdt") is None:
            await render(
                update,
                context,
                cards.error_card(
                    problem="Incomplete quote",
                    cause="THB/USDT missing.",
                    action="Edit amounts before confirm.",
                ),
            )
            return
        entry = store.update(ledger_id, status=Status.WAITING_USDT.value)
        assert entry
        await _show_confirmation(update, context, entry)
        return

    if action == "settle":
        await answer_callback(update, "Settled")
        if not entry:
            await render(
                update,
                context,
                cards.error_card(
                    problem="Not found",
                    cause="Nothing to settle.",
                    action="Open a new entry.",
                ),
            )
            return
        settled = store.record_settlement(ledger_id)
        if not settled:
            await render(
                update,
                context,
                cards.error_card(
                    problem="Settle failed",
                    cause="Ledger could not record settlement.",
                    action="Retry /status on this id.",
                ),
            )
            return
        bal = store.get_balance()
        _sessions(context).update(
            update.effective_chat.id, active_ledger_id=None, mode="idle"
        )
        await render(
            update,
            context,
            cards.success_card(
                ledger_id=settled["id"],
                profit_pct=settled.get("profit_pct"),
                profit_thb=None,
                balance_usdt=bal,
            ),
            keyboard=keyboards.done_keyboard(),
        )
        return

    if action == "edit":
        await answer_callback(update, "Edit mode")
        if not entry:
            await render(
                update,
                context,
                cards.error_card(
                    problem="Not found",
                    cause="Cannot edit missing ledger.",
                    action="Start over.",
                ),
            )
            return
        _sessions(context).update(
            update.effective_chat.id,
            active_ledger_id=ledger_id,
            mode="edit",
        )
        await render(
            update,
            context,
            cards.edit_card(
                ledger_id=entry["id"],
                thb=entry.get("thb"),
                usdt=entry.get("usdt"),
                bank=entry.get("bank"),
                last4=entry.get("last4"),
            ),
            keyboard=keyboards.edit_done_keyboard(ledger_id),
        )
        return

    if action == "cancel":
        await answer_callback(update, "Cancelled")
        if entry and _entry_status(entry) != Status.SETTLED.value:
            store.delete(ledger_id)
        _sessions(context).update(
            update.effective_chat.id, active_ledger_id=None, mode="idle"
        )
        await show_home(update, context)
        return

    if action == "delete_yes":
        await answer_callback(update, "Deleted")
        store.delete(ledger_id)
        _sessions(context).update(
            update.effective_chat.id, active_ledger_id=None, mode="idle"
        )
        await render(
            update,
            context,
            cards.success_card(
                ledger_id=ledger_id,
                profit_pct=None,
                profit_thb=None,
                badge="REMOVED",
                closing="Deleted.",
            ),
            keyboard=keyboards.done_keyboard(),
        )
        return

    if action in {"delete_no", "back"}:
        await answer_callback(update, "Kept")
        if entry:
            await _show_entry_card(update, context, entry)
        else:
            await show_home(update, context)
        return

    await answer_callback(update)
