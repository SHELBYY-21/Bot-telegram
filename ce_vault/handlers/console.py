"""CE VAULT console handlers — one card, one decision, edit-in-place."""

from __future__ import annotations

import logging
import os
import re
from decimal import Decimal
from typing import Any

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from ce_vault.ledger import LedgerEntry, LedgerStore, utcnow
from ce_vault.ocr import (
    detect_repeated_receiver,
    extract_from_image,
    image_hash,
    parse_slip_text,
)
from ce_vault.rates import RateService, profit_pct
from ce_vault.theme import mask_account, money_code, pct, to_decimal
from ce_vault.ui import (
    ErrorView,
    HistoryView,
    OcrResultView,
    PipelineStatus,
    SuccessView,
    TxDraft,
    card_confirmation,
    card_console_home,
    card_delete,
    card_edit,
    card_error,
    card_history,
    card_loading,
    card_ocr,
    card_success,
    kb_confirm,
    kb_delete,
    kb_done,
    kb_edit,
    kb_home,
    kb_ocr_next,
)
from ce_vault.ui.status import render_single

logger = logging.getLogger("ce_vault")

USDT_RE = re.compile(
    r"^\s*(?:usdt\s*)?([0-9]+(?:\.[0-9]{1,6})?)\s*(?:usdt)?\s*$",
    re.IGNORECASE,
)
SELL_RATE_RE = re.compile(
    r"^\s*/?sell(?:rate)?\s+([0-9]+(?:\.[0-9]{1,4})?)\s*$",
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


def store(context: ContextTypes.DEFAULT_TYPE) -> LedgerStore:
    return context.application.bot_data["ledger"]


def rates(context: ContextTypes.DEFAULT_TYPE) -> RateService:
    return context.application.bot_data["rates"]


def session(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    return context.chat_data.setdefault("vault", {})


async def send_card(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    keyboard=None,
    edit: bool = True,
    ledger_id: str | None = None,
):
    """Prefer editing the previous console message — never spam."""
    assert update.effective_chat
    chat_id = update.effective_chat.id
    sess = session(context)
    message_id = sess.get("message_id")

    if edit and message_id:
        try:
            msg = await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
            if ledger_id:
                store(context).set_message(ledger_id, chat_id, msg.message_id)
            return msg
        except Exception as exc:
            logger.debug("edit failed, sending new: %s", exc)

    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
    sess["message_id"] = msg.message_id
    if ledger_id:
        store(context).set_message(ledger_id, chat_id, msg.message_id)
    return msg


async def reply_new(update: Update, text: str, keyboard=None):
    assert update.effective_message
    return await update.effective_message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    ls = store(context)
    home = card_console_home(
        ls.get_balance(),
        open_count=(
            ls.count_by_status(PipelineStatus.WAITING_USDT.value)
            + ls.count_by_status(PipelineStatus.OCR_VERIFIED.value)
            + ls.count_by_status(PipelineStatus.RECEIVED.value)
        ),
        settled_today=ls.count_settled_today(),
    )
    session(context).pop("editing", None)
    session(context).pop("active_ledger", None)
    msg = await reply_new(update, home, kb_home())
    session(context)["message_id"] = msg.message_id


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    text = "\n".join(
        [
            "<b>CE VAULT</b>",
            "<i>Secure Ledger</i>",
            "────────────────",
            "Send slip image",
            "or USDT amount",
            "",
            "<code>/start</code>  console",
            "<code>/ledger &lt;id&gt;</code>",
            "<code>/history &lt;bank&gt; &lt;last4&gt;</code>",
            "<code>/sell &lt;rate&gt;</code>",
            "<code>/rates</code>",
            "<code>/balance</code>",
            "<code>/open</code>",
            "<code>/delete &lt;id&gt;</code>",
        ]
    )
    await send_card(update, context, text, keyboard=kb_home(), edit=False)


async def cmd_rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    buy, sell = rates(context).current()
    text = "\n".join(
        [
            "<b>CE VAULT</b>",
            "<i>Rate Desk</i>",
            "────────────────",
            f"Buy Rate\n{money_code(buy, 2)}",
            f"Sell Rate\n{money_code(sell, 2)}",
            f"Profit\n<code>{pct(profit_pct(buy, sell))}</code>",
            "",
            "<i>Buy Rate is system-owned.</i>",
            "<i>/sell &lt;rate&gt; to update Sell.</i>",
        ]
    )
    await send_card(update, context, text, keyboard=kb_home())


async def cmd_sell(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not context.args:
        await send_card(
            update,
            context,
            card_error(ErrorView("Missing rate", "No sell rate provided", "/sell 40.00")),
            edit=False,
        )
        return
    try:
        rates(context).set(sell=to_decimal(context.args[0]))
    except Exception as exc:
        await send_card(
            update,
            context,
            card_error(ErrorView("Invalid rate", str(exc), "/sell 40.00")),
            edit=False,
        )
        return
    await cmd_rates(update, context)


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    bal = store(context).get_balance()
    text = "\n".join(
        [
            "<b>CE VAULT</b>",
            "<i>Treasury</i>",
            "────────────────",
            f"Updated Balance\n{money_code(bal, 4)} USDT",
        ]
    )
    await send_card(update, context, text, keyboard=kb_home())


async def cmd_open(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    await _list_status(update, context, PipelineStatus.WAITING_USDT.value)


async def cmd_ledger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not context.args:
        await send_card(
            update,
            context,
            card_error(ErrorView("Missing ID", "Ledger ID required", "/ledger LDG-…")),
            edit=False,
        )
        return
    entry = store(context).get(context.args[0].upper())
    if not entry:
        await send_card(
            update,
            context,
            card_error(
                ErrorView("Not found", f"No entry {context.args[0]}", "Check ID"),
                context.args[0].upper(),
            ),
            edit=False,
        )
        return
    draft = _draft_from_entry(entry)
    if entry.status == PipelineStatus.SETTLED.value:
        await send_card(
            update,
            context,
            card_success(
                SuccessView(
                    ledger_id=entry.ledger_id,
                    profit_pct=entry.profit,
                    balance_usdt=store(context).get_balance(),
                )
            ),
            keyboard=kb_done(entry.ledger_id),
            ledger_id=entry.ledger_id,
            edit=False,
        )
        return
    await send_card(
        update,
        context,
        card_confirmation(draft),
        keyboard=kb_confirm(entry.ledger_id),
        ledger_id=entry.ledger_id,
        edit=False,
    )


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not context.args or len(context.args) < 2:
        await send_card(
            update,
            context,
            card_error(
                ErrorView(
                    "Missing receiver",
                    "Bank and last4 required",
                    "/history SCB 3376",
                ),
            ),
            edit=False,
        )
        return
    bank, last4 = context.args[0].upper(), re.sub(r"\D", "", context.args[1])[-4:]
    hist = store(context).receiver_history(bank, last4)
    await send_card(
        update,
        context,
        card_history(HistoryView(**hist)),
        keyboard=kb_home(),
        edit=False,
    )


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not context.args:
        await send_card(
            update,
            context,
            card_error(ErrorView("Missing ID", "Ledger ID required", "/delete LDG-…")),
            edit=False,
        )
        return
    ledger_id = context.args[0].upper()
    entry = store(context).get(ledger_id)
    if not entry:
        await send_card(
            update,
            context,
            card_error(ErrorView("Not found", ledger_id, "Check ID"), ledger_id),
            edit=False,
        )
        return
    await send_card(
        update,
        context,
        card_delete(ledger_id, mask_account(entry.last4, entry.bank)),
        keyboard=kb_delete(ledger_id),
        ledger_id=ledger_id,
        edit=False,
    )


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update) or not update.effective_message:
        return
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)

    photo = update.effective_message.photo[-1]
    caption = update.effective_message.caption or ""
    tg_file = await context.bot.get_file(photo.file_id)
    image_bytes = bytes(await tg_file.download_as_bytearray())
    slip = image_hash(image_bytes)

    ls = store(context)
    dup = ls.find_by_slip_hash(slip)
    ledger_id = ls.new_ledger_id()

    loading = await send_card(
        update, context, card_loading(ledger_id, "Vision"), edit=False, ledger_id=ledger_id
    )
    session(context)["message_id"] = loading.message_id

    ocr = await extract_from_image(image_bytes, caption)
    staff = _staff_name(update)
    staff_id = update.effective_user.id if update.effective_user else None

    hist = ls.receiver_history(ocr.bank, ocr.last4)
    repeat_warn = detect_repeated_receiver(hist)
    warning = ocr.warning
    if dup:
        warning = f"Duplicate slip of {dup.ledger_id}"
        ocr.verified = False
    elif repeat_warn:
        warning = repeat_warn

    quote = rates(context).from_thb(ocr.amount_thb) if ocr.amount_thb > 0 else None

    entry = LedgerEntry(
        ledger_id=ledger_id,
        status=(
            PipelineStatus.OCR_VERIFIED.value
            if ocr.verified and not dup
            else PipelineStatus.RECEIVED.value
        ),
        thb=quote.thb if quote else ocr.amount_thb,
        usdt=quote.usdt if quote else Decimal("0"),
        buy_rate=quote.buy_rate if quote else Decimal("0"),
        sell_rate=quote.sell_rate if quote else Decimal("0"),
        profit=quote.profit_pct if quote else Decimal("0"),
        receiver=ocr.receiver,
        bank=ocr.bank,
        last4=ocr.last4,
        confidence=ocr.confidence,
        staff=staff,
        staff_id=staff_id,
        chat_id=update.effective_chat.id,
        message_id=loading.message_id,
        slip_hash=slip,
        slip_file_id=photo.file_id,
        ocr_raw=ocr.raw,
        images=[photo.file_id],
        history=[{"at": utcnow(), "event": "received", "detail": {"provider": ocr.provider}}],
    )
    ls.upsert(entry)
    session(context)["active_ledger"] = ledger_id

    view = OcrResultView(
        ledger_id=ledger_id,
        confidence=ocr.confidence,
        receiver=ocr.receiver,
        bank=ocr.bank,
        last4=ocr.last4,
        amount_thb=ocr.amount_thb,
        verified=ocr.verified and not dup,
        warning=warning,
        duplicate=bool(dup),
    )
    await send_card(
        update,
        context,
        card_ocr(view),
        keyboard=kb_ocr_next(ledger_id),
        ledger_id=ledger_id,
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update) or not update.effective_message:
        return
    text = (update.effective_message.text or "").strip()
    if not text or text.startswith("/"):
        return

    sess = session(context)
    if sess.get("editing"):
        await _apply_edit(update, context, text)
        return

    m_sell = SELL_RATE_RE.match(text)
    if m_sell:
        context.args = [m_sell.group(1)]
        await cmd_sell(update, context)
        return

    m = USDT_RE.match(text)
    if m:
        await _create_from_usdt(update, context, to_decimal(m.group(1)))
        return

    await _create_from_slip_text(update, context, text)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update) or not update.callback_query:
        return
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data == "nw":
        await cmd_start(update, context)
        return
    if data == "rt":
        await cmd_rates(update, context)
        return
    if data.startswith("ls:"):
        status = data.split(":", 1)[1]
        mapped = {
            "open": PipelineStatus.WAITING_USDT.value,
            "settled": PipelineStatus.SETTLED.value,
        }.get(status, status.upper())
        await _list_status(update, context, mapped)
        return

    action, _, ledger_id = data.partition(":")
    ledger_id = ledger_id.upper()
    handlers = {
        "oc": _cb_ocr_continue,
        "cf": _cb_confirm,
        "ed": _cb_edit,
        "cx": _cb_cancel,
        "dl": _cb_delete,
        "kp": _cb_keep,
        "hs": _cb_history,
    }
    fn = handlers.get(action)
    if fn:
        await fn(update, context, ledger_id)


async def _cb_ocr_continue(
    update: Update, context: ContextTypes.DEFAULT_TYPE, ledger_id: str
) -> None:
    entry = store(context).get(ledger_id)
    if not entry:
        await send_card(
            update,
            context,
            card_error(ErrorView("Not found", ledger_id, "Restart with /start"), ledger_id),
        )
        return
    if entry.thb <= 0:
        await send_card(
            update,
            context,
            card_error(
                ErrorView("No amount", "OCR missed THB", "Edit or resend slip"),
                ledger_id,
            ),
            keyboard=kb_edit(ledger_id),
            ledger_id=ledger_id,
        )
        session(context)["editing"] = ledger_id
        return

    if entry.usdt <= 0:
        quote = rates(context).from_thb(entry.thb)
        entry.thb = quote.thb
        entry.usdt = quote.usdt
        entry.buy_rate = quote.buy_rate
        entry.sell_rate = quote.sell_rate
        entry.profit = quote.profit_pct

    entry.status = PipelineStatus.WAITING_USDT.value
    store(context).upsert(entry)
    store(context).append_history(ledger_id, "ocr_continue")
    await send_card(
        update,
        context,
        card_confirmation(_draft_from_entry(entry)),
        keyboard=kb_confirm(ledger_id),
        ledger_id=ledger_id,
    )


async def _cb_confirm(
    update: Update, context: ContextTypes.DEFAULT_TYPE, ledger_id: str
) -> None:
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    ls = store(context)
    entry = ls.get(ledger_id)
    if not entry:
        await send_card(
            update,
            context,
            card_error(ErrorView("Not found", ledger_id, "Restart"), ledger_id),
        )
        return
    if entry.status == PipelineStatus.SETTLED.value:
        await send_card(
            update,
            context,
            card_success(SuccessView(ledger_id, entry.profit, ls.get_balance())),
            keyboard=kb_done(ledger_id),
            ledger_id=ledger_id,
        )
        return

    await send_card(update, context, card_loading(ledger_id, "Settling"), ledger_id=ledger_id)

    entry.status = PipelineStatus.SETTLED.value
    entry.settled_at = utcnow()
    ls.upsert(entry)
    bal = ls.adjust_balance(-entry.usdt)
    ls.append_history(ledger_id, "settled", {"usdt": str(entry.usdt)})

    session(context).pop("editing", None)
    session(context).pop("active_ledger", None)

    await send_card(
        update,
        context,
        card_success(SuccessView(ledger_id, entry.profit, bal)),
        keyboard=kb_done(ledger_id),
        ledger_id=ledger_id,
    )


async def _cb_edit(
    update: Update, context: ContextTypes.DEFAULT_TYPE, ledger_id: str
) -> None:
    entry = store(context).get(ledger_id)
    if not entry:
        return
    session(context)["editing"] = ledger_id
    entry.status = PipelineStatus.EDITING.value
    store(context).upsert(entry)
    await send_card(
        update,
        context,
        card_edit(_draft_from_entry(entry)),
        keyboard=kb_edit(ledger_id),
        ledger_id=ledger_id,
    )


async def _cb_cancel(
    update: Update, context: ContextTypes.DEFAULT_TYPE, ledger_id: str
) -> None:
    session(context).pop("editing", None)
    session(context).pop("active_ledger", None)
    entry = store(context).get(ledger_id)
    if entry and entry.status != PipelineStatus.SETTLED.value:
        store(context).delete(ledger_id)
    await send_card(
        update,
        context,
        card_error(
            ErrorView("Cancelled", f"{ledger_id} discarded", "Send slip or USDT"),
            ledger_id,
        ),
        keyboard=kb_home(),
        ledger_id=ledger_id,
    )


async def _cb_delete(
    update: Update, context: ContextTypes.DEFAULT_TYPE, ledger_id: str
) -> None:
    entry = store(context).get(ledger_id)
    if entry and entry.status == PipelineStatus.SETTLED.value:
        store(context).adjust_balance(entry.usdt)
    ok = store(context).delete(ledger_id)
    if not ok:
        await send_card(
            update,
            context,
            card_error(ErrorView("Not found", ledger_id, "Already removed"), ledger_id),
            keyboard=kb_home(),
        )
        return
    await send_card(
        update,
        context,
        "\n".join(
            [
                "<b>CE VAULT</b>",
                "<i>Secure Ledger</i>",
                "────────────────",
                render_single(PipelineStatus.DELETED, glow=True),
                "",
                f"Target\n<code>{ledger_id}</code>",
                "",
                "<i>Removed.</i>",
            ]
        ),
        keyboard=kb_home(),
    )


async def _cb_keep(
    update: Update, context: ContextTypes.DEFAULT_TYPE, ledger_id: str
) -> None:
    entry = store(context).get(ledger_id)
    if not entry:
        await cmd_start(update, context)
        return
    await send_card(
        update,
        context,
        card_confirmation(_draft_from_entry(entry)),
        keyboard=kb_confirm(ledger_id),
        ledger_id=ledger_id,
    )


async def _cb_history(
    update: Update, context: ContextTypes.DEFAULT_TYPE, ledger_id: str
) -> None:
    entry = store(context).get(ledger_id)
    if not entry:
        await send_card(
            update,
            context,
            card_error(ErrorView("Not found", ledger_id, "Restart"), ledger_id),
        )
        return
    hist = store(context).receiver_history(entry.bank, entry.last4)
    await send_card(
        update,
        context,
        card_history(HistoryView(**hist), ledger_id),
        keyboard=kb_done(ledger_id),
        ledger_id=ledger_id,
    )


async def _create_from_usdt(
    update: Update, context: ContextTypes.DEFAULT_TYPE, usdt: Decimal
) -> None:
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    ls = store(context)
    ledger_id = ls.new_ledger_id()
    quote = rates(context).from_usdt(usdt)
    entry = LedgerEntry(
        ledger_id=ledger_id,
        status=PipelineStatus.WAITING_USDT.value,
        thb=quote.thb,
        usdt=quote.usdt,
        buy_rate=quote.buy_rate,
        sell_rate=quote.sell_rate,
        profit=quote.profit_pct,
        receiver="MANUAL",
        bank="MANUAL",
        last4="0000",
        confidence=None,
        staff=_staff_name(update),
        staff_id=update.effective_user.id if update.effective_user else None,
        chat_id=update.effective_chat.id,
        history=[{"at": utcnow(), "event": "usdt_input", "detail": {"usdt": str(usdt)}}],
    )
    ls.upsert(entry)
    session(context)["active_ledger"] = ledger_id
    await send_card(
        update,
        context,
        card_confirmation(_draft_from_entry(entry)),
        keyboard=kb_confirm(ledger_id),
        ledger_id=ledger_id,
        edit=False,
    )


async def _create_from_slip_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
) -> None:
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    ocr = parse_slip_text(text)
    ls = store(context)
    ledger_id = ls.new_ledger_id()
    quote = rates(context).from_thb(ocr.amount_thb) if ocr.amount_thb > 0 else None
    hist = ls.receiver_history(ocr.bank, ocr.last4)
    warning = ocr.warning or detect_repeated_receiver(hist)

    entry = LedgerEntry(
        ledger_id=ledger_id,
        status=(
            PipelineStatus.OCR_VERIFIED.value if ocr.verified else PipelineStatus.RECEIVED.value
        ),
        thb=quote.thb if quote else ocr.amount_thb,
        usdt=quote.usdt if quote else Decimal("0"),
        buy_rate=quote.buy_rate if quote else Decimal("0"),
        sell_rate=quote.sell_rate if quote else Decimal("0"),
        profit=quote.profit_pct if quote else Decimal("0"),
        receiver=ocr.receiver,
        bank=ocr.bank,
        last4=ocr.last4,
        confidence=ocr.confidence,
        staff=_staff_name(update),
        staff_id=update.effective_user.id if update.effective_user else None,
        chat_id=update.effective_chat.id,
        ocr_raw=ocr.raw,
        history=[{"at": utcnow(), "event": "text_slip", "detail": {}}],
    )
    ls.upsert(entry)
    session(context)["active_ledger"] = ledger_id

    view = OcrResultView(
        ledger_id=ledger_id,
        confidence=ocr.confidence,
        receiver=ocr.receiver,
        bank=ocr.bank,
        last4=ocr.last4,
        amount_thb=ocr.amount_thb,
        verified=ocr.verified,
        warning=warning,
    )
    await send_card(
        update,
        context,
        card_ocr(view),
        keyboard=kb_ocr_next(ledger_id),
        ledger_id=ledger_id,
        edit=False,
    )


async def _apply_edit(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
) -> None:
    ledger_id = session(context).get("editing")
    if not ledger_id:
        return
    entry = store(context).get(ledger_id)
    if not entry:
        session(context).pop("editing", None)
        return

    m = USDT_RE.match(text)
    thb_m = re.match(
        r"^\s*(?:thb\s*)?([0-9]+(?:\.[0-9]{1,2})?)\s*(?:thb|บาท)?\s*$", text, re.I
    )

    try:
        if m:
            quote = rates(context).from_usdt(to_decimal(m.group(1)))
        elif thb_m:
            quote = rates(context).from_thb(to_decimal(thb_m.group(1)))
        else:
            await send_card(
                update,
                context,
                card_error(
                    ErrorView("Invalid input", "Expected USDT or THB amount", "12.5342"),
                    ledger_id,
                ),
                keyboard=kb_edit(ledger_id),
                ledger_id=ledger_id,
            )
            return
    except Exception as exc:
        await send_card(
            update,
            context,
            card_error(ErrorView("Calc failed", str(exc), "Retry amount"), ledger_id),
            keyboard=kb_edit(ledger_id),
            ledger_id=ledger_id,
        )
        return

    entry.thb = quote.thb
    entry.usdt = quote.usdt
    entry.buy_rate = quote.buy_rate
    entry.sell_rate = quote.sell_rate
    entry.profit = quote.profit_pct
    entry.status = PipelineStatus.WAITING_USDT.value
    store(context).upsert(entry)
    store(context).append_history(ledger_id, "edited", {"usdt": str(entry.usdt)})
    session(context).pop("editing", None)

    await send_card(
        update,
        context,
        card_confirmation(_draft_from_entry(entry)),
        keyboard=kb_confirm(ledger_id),
        ledger_id=ledger_id,
    )


async def _list_status(
    update: Update, context: ContextTypes.DEFAULT_TYPE, status: str
) -> None:
    entries = store(context).list_by_status(status, limit=8)
    if not entries:
        await send_card(
            update,
            context,
            card_error(ErrorView("Empty", f"No {status} entries", "Send slip or USDT")),
            keyboard=kb_home(),
        )
        return
    lines = [
        "<b>CE VAULT</b>",
        f"<i>{status}</i>",
        "────────────────",
    ]
    for e in entries:
        lines.append(
            f"<code>{e.ledger_id}</code>\n"
            f"{money_code(e.thb, 2)} THB  ·  {money_code(e.usdt, 4)} USDT"
        )
        lines.append("")
    await send_card(update, context, "\n".join(lines).rstrip(), keyboard=kb_home())


def _draft_from_entry(entry: LedgerEntry) -> TxDraft:
    pipeline = {
        PipelineStatus.RECEIVED.value,
        PipelineStatus.OCR_VERIFIED.value,
        PipelineStatus.WAITING_USDT.value,
        PipelineStatus.SETTLED.value,
    }
    status = (
        PipelineStatus(entry.status)
        if entry.status in pipeline
        else PipelineStatus.WAITING_USDT
    )
    return TxDraft(
        ledger_id=entry.ledger_id,
        thb=entry.thb,
        usdt=entry.usdt,
        buy_rate=entry.buy_rate,
        sell_rate=entry.sell_rate,
        profit_pct=entry.profit,
        receiver=entry.receiver,
        bank=entry.bank,
        last4=entry.last4,
        confidence=entry.confidence,
        status=status,
        staff=entry.staff,
    )


def _staff_name(update: Update) -> str:
    user = update.effective_user
    if not user:
        return "system"
    return user.username or user.full_name or str(user.id)
