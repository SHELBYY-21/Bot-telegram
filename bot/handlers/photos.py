"""Photo/slip handlers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.auth import authorized
from bot.keyboards import confirm_keyboard, history_keyboard
from bot.messaging import send_card, typing
from cards.confirmation import confirmation_card
from cards.error import error_card
from cards.history import history_card
from cards.ocr import ocr_card
from cards.receive import loading_card
from services.ledger import LedgerService, save_slip_image
from services.ocr import process_slip

logger = logging.getLogger(__name__)


def _ledger(context: ContextTypes.DEFAULT_TYPE) -> LedgerService:
    return context.application.bot_data["ledger"]


async def _process_slip_bytes(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    image_data: bytes,
    caption: str | None = None,
) -> None:
    assert update.effective_user
    staff_id = update.effective_user.id
    ledger = _ledger(context)

    await typing(update, context)

    tx = ledger.start_from_slip(staff_id, image_data, "")
    ledger_id = tx["id"]

    if tx.get("_duplicate"):
        existing_id = tx["id"]
        await send_card(
            update, context,
            error_card(
                "Duplicate Slip",
                f"Slip already recorded as {existing_id}",
                "Verify or use a different slip",
            ),
        )
        return

    image_path = save_slip_image(image_data, ledger_id, SLIPS_DIR)
    ledger.repo.update_transaction(ledger_id, image_path=image_path)

    await send_card(update, context, loading_card(ledger_id))
    await typing(update, context)

    ocr_result = await process_slip(image_data, caption)
    ocr_dict = ocr_result.to_dict()

    if ocr_result.bank and ocr_result.last4:
        receiver = ledger.get_receiver_history(ocr_result.bank, ocr_result.last4)
        if receiver:
            ocr_dict["_known_receiver"] = True
            ocr_dict["_receiver_history"] = receiver

    tx = ledger.apply_ocr(ledger_id, ocr_dict)
    if not tx:
        await send_card(
            update, context,
            error_card("Processing Failed", "Could not update transaction", "Try again"),
            edit=True,
        )
        return

    context.chat_data["pending_ledger"] = ledger_id

    await send_card(update, context, ocr_card(tx, ocr_dict), edit=True)
    await typing(update, context)

    keyboard = confirm_keyboard(ledger_id)
    if ocr_dict.get("_known_receiver") and ocr_dict.get("_receiver_history"):
        receiver = ocr_dict["_receiver_history"]
        risk = ledger.assess_risk(receiver)
        await send_card(update, context, history_card(receiver, risk), edit=True)
        keyboard = history_keyboard(ledger_id, receiver["id"])

    await send_card(update, context, confirmation_card(tx, ocr_dict), keyboard=keyboard, edit=True)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return

    assert update.effective_message
    photo = update.effective_message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_data = bytes(await file.download_as_bytearray())
    caption = update.effective_message.caption
    await _process_slip_bytes(update, context, image_data, caption)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle slip sent as document/image file."""
    if not authorized(update):
        return
    doc = update.effective_message.document
    if not doc or not doc.mime_type or not doc.mime_type.startswith("image/"):
        await send_card(
            update, context,
            error_card("Invalid File", "Only image files accepted", "Send a slip photo"),
        )
        return
    file = await context.bot.get_file(doc.file_id)
    image_data = bytes(await file.download_as_bytearray())
    caption = update.effective_message.caption
    await _process_slip_bytes(update, context, image_data, caption)
