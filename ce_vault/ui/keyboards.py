"""Inline keyboards — one decision set per card."""

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


def ocr_keyboard(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Continue", callback_data=f"tx:quote:{ledger_id}"),
                InlineKeyboardButton("Edit", callback_data=f"tx:edit:{ledger_id}"),
                InlineKeyboardButton("Cancel", callback_data=f"tx:cancel:{ledger_id}"),
            ]
        ]
    )


def edit_field_keyboard(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("THB", callback_data=f"tx:editfield:{ledger_id}:amount"),
                InlineKeyboardButton("USDT", callback_data=f"tx:editfield:{ledger_id}:usdt"),
            ],
            [
                InlineKeyboardButton("Receiver", callback_data=f"tx:editfield:{ledger_id}:receiver"),
                InlineKeyboardButton("Bank", callback_data=f"tx:editfield:{ledger_id}:bank"),
            ],
            [
                InlineKeyboardButton("Last4", callback_data=f"tx:editfield:{ledger_id}:last4"),
                InlineKeyboardButton("Back", callback_data=f"tx:back:{ledger_id}"),
            ],
        ]
    )


def delete_keyboard(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Void", callback_data=f"tx:void:{ledger_id}"),
                InlineKeyboardButton("Keep", callback_data=f"tx:back:{ledger_id}"),
            ]
        ]
    )


def settle_keyboard(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Mark Settled", callback_data=f"tx:settle:{ledger_id}"),
                InlineKeyboardButton("Void", callback_data=f"tx:delete:{ledger_id}"),
            ]
        ]
    )


def done_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("New Intake", callback_data="console:home")]]
    )
