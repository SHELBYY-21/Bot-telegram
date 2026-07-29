"""Inline keyboards — one decision surface per card."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def confirm_keyboard(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Confirm", callback_data=f"tx:confirm:{ledger_id}"),
                InlineKeyboardButton("Edit", callback_data=f"tx:edit:{ledger_id}"),
                InlineKeyboardButton("Cancel", callback_data=f"tx:cancel:{ledger_id}"),
            ]
        ]
    )


def edit_fields_keyboard(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("THB", callback_data=f"edit:thb:{ledger_id}"),
                InlineKeyboardButton("USDT", callback_data=f"edit:usdt:{ledger_id}"),
            ],
            [
                InlineKeyboardButton("Receiver", callback_data=f"edit:receiver:{ledger_id}"),
                InlineKeyboardButton("Bank", callback_data=f"edit:bank:{ledger_id}"),
            ],
            [
                InlineKeyboardButton("Last4", callback_data=f"edit:last4:{ledger_id}"),
                InlineKeyboardButton("Back", callback_data=f"tx:back:{ledger_id}"),
            ],
        ]
    )


def settle_keyboard(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Mark Settled", callback_data=f"tx:settle:{ledger_id}"),
                InlineKeyboardButton("Cancel", callback_data=f"tx:cancel:{ledger_id}"),
            ]
        ]
    )


def delete_keyboard(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Delete", callback_data=f"tx:delete:{ledger_id}"),
                InlineKeyboardButton("Keep", callback_data=f"tx:back:{ledger_id}"),
            ]
        ]
    )


def done_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("New Entry", callback_data="tx:new")]]
    )
