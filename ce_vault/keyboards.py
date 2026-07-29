"""Inline keyboards — one decision per screen."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def confirm_keyboard(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Confirm", callback_data=f"confirm:{ledger_id}"),
                InlineKeyboardButton("Edit", callback_data=f"edit:{ledger_id}"),
                InlineKeyboardButton("Cancel", callback_data=f"cancel:{ledger_id}"),
            ]
        ]
    )


def ocr_keyboard(ledger_id: str, *, warn: bool = False) -> InlineKeyboardMarkup:
    primary = "Review" if warn else "Continue"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(primary, callback_data=f"ocr_ok:{ledger_id}"),
                InlineKeyboardButton("Edit", callback_data=f"edit:{ledger_id}"),
                InlineKeyboardButton("Cancel", callback_data=f"cancel:{ledger_id}"),
            ]
        ]
    )


def delete_keyboard(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Delete", callback_data=f"delete_yes:{ledger_id}"),
                InlineKeyboardButton("Keep", callback_data=f"delete_no:{ledger_id}"),
            ]
        ]
    )


def edit_done_keyboard(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Confirm", callback_data=f"confirm:{ledger_id}"),
                InlineKeyboardButton("Cancel", callback_data=f"cancel:{ledger_id}"),
            ]
        ]
    )


def settle_keyboard(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Mark Settled", callback_data=f"settle:{ledger_id}"),
                InlineKeyboardButton("Cancel", callback_data=f"cancel:{ledger_id}"),
            ]
        ]
    )


def done_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("New Entry", callback_data="home")]]
    )
