"""Inline keyboard builders."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def confirm_keyboard(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Confirm", callback_data=f"confirm:{ledger_id}"),
            InlineKeyboardButton("Edit", callback_data=f"edit:{ledger_id}"),
            InlineKeyboardButton("Cancel", callback_data=f"cancel:{ledger_id}"),
        ],
    ])


def edit_keyboard(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("USDT Amount", callback_data=f"edit_usdt:{ledger_id}"),
            InlineKeyboardButton("Back", callback_data=f"back:{ledger_id}"),
        ],
    ])


def history_keyboard(ledger_id: str, receiver_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("View History", callback_data=f"history:{receiver_id}"),
            InlineKeyboardButton("Confirm", callback_data=f"confirm:{ledger_id}"),
        ],
        [
            InlineKeyboardButton("Edit", callback_data=f"edit:{ledger_id}"),
            InlineKeyboardButton("Cancel", callback_data=f"cancel:{ledger_id}"),
        ],
    ])


def done_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("New Transaction", callback_data="new_tx")],
    ])
