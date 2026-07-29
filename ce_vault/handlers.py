"""Telegram handlers for the CE VAULT operations console."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from ce_vault import cards, keyboards
from ce_vault.console import answer_callback, render, show_typing
from ce_vault.ledger import Ledger, LedgerEntry, new_ledger_id, slip_hash_bytes
from ce_vault.ocr import OcrResult, extract_from_text, parse_edit_command, parse_usdt_amount
from ce_vault.rates import RateEngine

logger = logging.getLogger("ce_vault.handlers")


def _ledger(context: ContextTypes.DEFAULT_TYPE) -> Ledger:
    return context.application.bot_data["ledger"]


def _rates(context: ContextTypes.DEFAULT_TYPE) -> RateEngine:
    return context.application.bot_data["rates"]


def _sessions(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["sessions"]


def _settings(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["settings"]


def _ocr(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["ocr"]


def authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    allowed = _settings(context).allowed_user_ids
    if not allowed:
        return True
    user = update.effective_user
    return bool(user) and user.id in allowed


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    await show_home(update, context, reset=True)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    await show_home(update, context)


async def show_home(
    update: Update, context: ContextTypes.DEFAULT_TYPE, *, reset: bool = False
) -> None:
    chat_id = update.effective_chat.id
    if reset:
        # Keep console_message_id so we edit the same surface into home.
        _sessions(context).update(
            chat_id,
            active_ledger_id=None,
            mode="idle",
            draft={},
        )
    rates = _rates(context)
    bal = _ledger(context).vault_balance()
    text = cards.console_home(
        buy_rate=float(rates.buy_rate),
        sell_rate=float(rates.sell_rate),
        balance=bal,
    )
    await render(update, context, text, prefer_edit=True)


async def cmd_rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    await show_home(update, context)


async def cmd_ledger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    entries = _ledger(context).recent(8)
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
        bank = ""
    else:
        sess = _sessions(context).get(update.effective_chat.id)
        if sess.active_ledger_id:
            entry = _ledger(context).get(sess.active_ledger_id)
            if entry:
                bank, last4 = entry.bank, entry.last4
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
            bank=hist["bank"],
            last4=hist["last4"],
            tx_count=int(hist["tx_count"]),
            total_thb=float(hist["total_thb"]),
            total_usdt=float(hist["total_usdt"]),
            first_seen=hist.get("first_seen"),
            last_seen=hist.get("last_seen"),
            receiver_name=hist.get("receiver_name"),
        ),
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    ledger_id = (context.args or [None])[0]
    if not ledger_id:
        sess = _sessions(context).get(update.effective_chat.id)
        ledger_id = sess.active_ledger_id
    if not ledger_id:
        await render(
            update,
            context,
            cards.error_card(
                problem="No active ledger",
                cause="Status requires a ledger id.",
                action="Usage: /status LED-…",
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
                action="Usage: /delete LED-…",
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
            ledger_id=entry.ledger_id,
            thb=entry.thb,
            bank=entry.bank,
            last4=entry.last4,
        ),
        keyboard=keyboards.delete_keyboard(entry.ledger_id),
    )


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update, context):
        return
    assert update.effective_message and update.effective_message.photo
    await show_typing(update, context)
    await render(update, context, cards.loading_card(phase="Vision"), prefer_edit=True)

    photo = update.effective_message.photo[-1]
    tg_file = await context.bot.get_file(photo.file_id)
    image_bytes = bytes(await tg_file.download_as_bytearray())
    slip_hash = slip_hash_bytes(image_bytes)

    settings = _settings(context)
    settings.images_dir.mkdir(parents=True, exist_ok=True)

    ledger = _ledger(context)
    duplicate = ledger.find_by_slip_hash(slip_hash)

    ocr_result: OcrResult = await _ocr(context).extract(image_bytes, mime="image/jpeg")
    # Caption may carry hints
    caption = update.effective_message.caption or ""
    if caption.strip():
        caption_ocr = extract_from_text(caption)
        ocr_result = _merge_ocr(ocr_result, caption_ocr)

    warn = ocr_result.confidence < settings.ocr_warn_below
    staff = update.effective_user
    ledger_id = new_ledger_id()
    image_path = settings.images_dir / f"{ledger_id}.jpg"
    image_path.write_bytes(image_bytes)

    quote = None
    if ocr_result.amount:
        quote = _rates(context).from_thb(ocr_result.amount)

    repeat_count = 0
    if ocr_result.bank and ocr_result.last4:
        repeat_count = ledger.count_receiver(ocr_result.bank, ocr_result.last4)

    entry = LedgerEntry(
        ledger_id=ledger_id,
        status="OCR VERIFIED" if ocr_result.verified and not warn else "RECEIVED",
        thb=float(quote.thb) if quote else ocr_result.amount,
        usdt=float(quote.usdt) if quote else None,
        buy_rate=float(quote.buy_rate) if quote else float(_rates(context).buy_rate),
        sell_rate=float(quote.sell_rate) if quote else float(_rates(context).sell_rate),
        profit_pct=float(quote.profit_pct) if quote else None,
        profit_thb=float(quote.profit_thb) if quote else None,
        receiver_name=ocr_result.receiver_name,
        bank=ocr_result.bank,
        last4=ocr_result.last4,
        ocr_confidence=ocr_result.confidence,
        ocr_raw={"source": ocr_result.source, "fields": ocr_result.fields, "text": ocr_result.raw_text},
        slip_hash=slip_hash,
        image_path=str(image_path),
        staff_id=staff.id if staff else None,
        staff_name=staff.full_name if staff else None,
        notes="duplicate_slip" if duplicate else None,
    )
    ledger.create(entry)
    _sessions(context).update(
        update.effective_chat.id,
        active_ledger_id=ledger_id,
        mode="idle",
        draft={},
    )

    text = cards.ocr_card(
        ledger_id=ledger_id,
        confidence=ocr_result.confidence,
        receiver_name=ocr_result.receiver_name,
        bank=ocr_result.bank,
        last4=ocr_result.last4,
        amount=ocr_result.amount,
        verified=ocr_result.verified and not warn,
        warn=warn,
        duplicate=bool(duplicate),
        repeat_receiver=repeat_count > 0,
        repeat_count=repeat_count,
    )
    await render(
        update,
        context,
        text,
        keyboard=keyboards.ocr_keyboard(ledger_id, warn=warn or bool(duplicate)),
    )


def _merge_ocr(primary: OcrResult, secondary: OcrResult) -> OcrResult:
    return OcrResult(
        receiver_name=primary.receiver_name or secondary.receiver_name,
        bank=primary.bank or secondary.bank,
        last4=primary.last4 or secondary.last4,
        amount=primary.amount if primary.amount is not None else secondary.amount,
        confidence=max(primary.confidence, secondary.confidence * 0.9),
        raw_text=primary.raw_text or secondary.raw_text,
        fields={**secondary.fields, **primary.fields},
        source=primary.source,
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

    # Structured slip paste (no image)
    if any(k in text.lower() for k in ("thb", "บาท", "bank", "scb", "kbank", "นาย", "นาง")):
        await _ingest_text_slip(update, context, text)
        return

    usdt = parse_usdt_amount(text)
    if usdt is not None:
        await _ingest_usdt(update, context, usdt)
        return

    await render(
        update,
        context,
        cards.error_card(
            problem="Unrecognized input",
            cause="Console expects a slip image or a USDT amount.",
            action="Example: 12.5   or   USDT 12.5",
        ),
    )


async def _ingest_usdt(
    update: Update, context: ContextTypes.DEFAULT_TYPE, usdt: float
) -> None:
    await show_typing(update, context)
    await render(update, context, cards.loading_card(phase="Quote"), prefer_edit=True)
    quote = _rates(context).from_usdt(usdt)
    staff = update.effective_user
    ledger_id = new_ledger_id()
    entry = LedgerEntry(
        ledger_id=ledger_id,
        status="WAITING USDT",
        thb=float(quote.thb),
        usdt=float(quote.usdt),
        buy_rate=float(quote.buy_rate),
        sell_rate=float(quote.sell_rate),
        profit_pct=float(quote.profit_pct),
        profit_thb=float(quote.profit_thb),
        staff_id=staff.id if staff else None,
        staff_name=staff.full_name if staff else None,
    )
    _ledger(context).create(entry)
    _sessions(context).update(
        update.effective_chat.id, active_ledger_id=ledger_id, mode="idle"
    )
    await render(
        update,
        context,
        cards.confirmation_card(
            ledger_id=ledger_id,
            thb=float(quote.thb),
            usdt=float(quote.usdt),
            buy_rate=float(quote.buy_rate),
            sell_rate=float(quote.sell_rate),
            profit_pct=float(quote.profit_pct),
            bank=None,
            last4=None,
            status="WAITING USDT",
        ),
        keyboard=keyboards.confirm_keyboard(ledger_id),
    )


async def _ingest_text_slip(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
) -> None:
    await show_typing(update, context)
    await render(update, context, cards.loading_card(phase="Parse"), prefer_edit=True)
    ocr_result = extract_from_text(text)
    settings = _settings(context)
    warn = ocr_result.confidence < settings.ocr_warn_below
    quote = _rates(context).from_thb(ocr_result.amount) if ocr_result.amount else None
    staff = update.effective_user
    ledger_id = new_ledger_id()
    repeat_count = 0
    if ocr_result.bank and ocr_result.last4:
        repeat_count = _ledger(context).count_receiver(ocr_result.bank, ocr_result.last4)

    entry = LedgerEntry(
        ledger_id=ledger_id,
        status="OCR VERIFIED" if ocr_result.verified and not warn else "RECEIVED",
        thb=float(quote.thb) if quote else ocr_result.amount,
        usdt=float(quote.usdt) if quote else None,
        buy_rate=float(quote.buy_rate) if quote else float(_rates(context).buy_rate),
        sell_rate=float(quote.sell_rate) if quote else float(_rates(context).sell_rate),
        profit_pct=float(quote.profit_pct) if quote else None,
        profit_thb=float(quote.profit_thb) if quote else None,
        receiver_name=ocr_result.receiver_name,
        bank=ocr_result.bank,
        last4=ocr_result.last4,
        ocr_confidence=ocr_result.confidence,
        ocr_raw={"source": "text", "text": text},
        staff_id=staff.id if staff else None,
        staff_name=staff.full_name if staff else None,
    )
    _ledger(context).create(entry)
    _sessions(context).update(
        update.effective_chat.id, active_ledger_id=ledger_id, mode="idle"
    )
    await render(
        update,
        context,
        cards.ocr_card(
            ledger_id=ledger_id,
            confidence=ocr_result.confidence,
            receiver_name=ocr_result.receiver_name,
            bank=ocr_result.bank,
            last4=ocr_result.last4,
            amount=ocr_result.amount,
            verified=ocr_result.verified and not warn,
            warn=warn,
            repeat_receiver=repeat_count > 0,
            repeat_count=repeat_count,
        ),
        keyboard=keyboards.ocr_keyboard(ledger_id, warn=warn),
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
    entry = _ledger(context).get(ledger_id)
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

    thb = patch.get("thb", entry.thb)
    usdt = patch.get("usdt")
    bank = patch.get("bank", entry.bank)
    last4 = patch.get("last4", entry.last4)

    rates = _rates(context)
    if usdt is not None:
        quote = rates.from_usdt(usdt)
    elif thb is not None:
        quote = rates.from_thb(thb)
    else:
        quote = None

    fields = {
        "bank": bank,
        "last4": last4,
        "event": "edited",
    }
    if quote:
        fields.update(
            {
                "thb": float(quote.thb),
                "usdt": float(quote.usdt),
                "buy_rate": float(quote.buy_rate),
                "sell_rate": float(quote.sell_rate),
                "profit_pct": float(quote.profit_pct),
                "profit_thb": float(quote.profit_thb),
            }
        )
    entry = _ledger(context).update(ledger_id, **fields)
    _sessions(context).update(update.effective_chat.id, mode="idle")
    assert entry
    # One card only — show confirmation after edit
    await _show_confirmation(update, context, entry)


async def _show_entry_card(
    update: Update, context: ContextTypes.DEFAULT_TYPE, entry: LedgerEntry
) -> None:
    if entry.status == "SETTLED":
        bal = _ledger(context).vault_balance()
        await render(
            update,
            context,
            cards.success_card(
                ledger_id=entry.ledger_id,
                profit_pct=entry.profit_pct,
                profit_thb=entry.profit_thb,
                balance_thb=bal["thb"],
                balance_usdt=bal["usdt"],
            ),
            keyboard=keyboards.done_keyboard(),
        )
        return
    await _show_confirmation(update, context, entry)


async def _show_confirmation(
    update: Update, context: ContextTypes.DEFAULT_TYPE, entry: LedgerEntry
) -> None:
    rates = _rates(context)
    if entry.thb is None or entry.usdt is None:
        await render(
            update,
            context,
            cards.receive_card(
                ledger_id=entry.ledger_id,
                thb=entry.thb,
                usdt=entry.usdt,
                buy_rate=entry.buy_rate or float(rates.buy_rate),
                sell_rate=entry.sell_rate or float(rates.sell_rate),
                bank=entry.bank,
                last4=entry.last4,
                status=entry.status,
                hint="Awaiting amount",
            ),
            keyboard=keyboards.confirm_keyboard(entry.ledger_id),
        )
        return
    await render(
        update,
        context,
        cards.confirmation_card(
            ledger_id=entry.ledger_id,
            thb=float(entry.thb),
            usdt=float(entry.usdt),
            buy_rate=float(entry.buy_rate or rates.buy_rate),
            sell_rate=float(entry.sell_rate or rates.sell_rate),
            profit_pct=float(entry.profit_pct or 0),
            bank=entry.bank,
            last4=entry.last4,
            confidence=entry.ocr_confidence,
            status=entry.status if entry.status != "RECEIVED" else "OCR VERIFIED",
        ),
        keyboard=keyboards.confirm_keyboard(entry.ledger_id),
    )


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
    ledger = _ledger(context)
    entry = ledger.get(ledger_id)

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
        if entry.thb is not None and entry.usdt is None:
            quote = _rates(context).from_thb(entry.thb)
            entry = ledger.update(
                ledger_id,
                thb=float(quote.thb),
                usdt=float(quote.usdt),
                buy_rate=float(quote.buy_rate),
                sell_rate=float(quote.sell_rate),
                profit_pct=float(quote.profit_pct),
                profit_thb=float(quote.profit_thb),
                status="OCR VERIFIED",
                event="quoted",
            )
        else:
            entry = ledger.update(
                ledger_id, status="OCR VERIFIED", event="ocr_continue"
            )
        assert entry
        await _show_confirmation(update, context, entry)
        return

    if action == "confirm":
        await answer_callback(update, "Settled")
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
        if entry.thb is None or entry.usdt is None:
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
        entry = ledger.update(ledger_id, status="SETTLED", event="settled")
        assert entry
        bal = ledger.vault_balance()
        _sessions(context).update(
            update.effective_chat.id, active_ledger_id=None, mode="idle"
        )
        await render(
            update,
            context,
            cards.success_card(
                ledger_id=entry.ledger_id,
                profit_pct=entry.profit_pct,
                profit_thb=entry.profit_thb,
                balance_thb=bal["thb"],
                balance_usdt=bal["usdt"],
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
                ledger_id=entry.ledger_id,
                thb=entry.thb,
                usdt=entry.usdt,
                bank=entry.bank,
                last4=entry.last4,
            ),
            keyboard=keyboards.edit_done_keyboard(ledger_id),
        )
        return

    if action == "cancel":
        await answer_callback(update, "Cancelled")
        if entry and entry.status != "SETTLED":
            ledger.delete(ledger_id)
        _sessions(context).update(
            update.effective_chat.id,
            active_ledger_id=None,
            mode="idle",
        )
        await show_home(update, context)
        return

    if action == "delete_yes":
        await answer_callback(update, "Deleted")
        ledger.delete(ledger_id)
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

    if action == "delete_no":
        await answer_callback(update, "Kept")
        if entry:
            await _show_entry_card(update, context, entry)
        else:
            await show_home(update, context)
        return

    await answer_callback(update)
