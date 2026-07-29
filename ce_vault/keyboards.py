"""Inline keyboards — decision surfaces for a single card."""

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


def edit_keyboard(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("THB", callback_data=f"tx:edit_thb:{ledger_id}"),
                InlineKeyboardButton("Receiver", callback_data=f"tx:edit_recv:{ledger_id}"),
            ],
            [
                InlineKeyboardButton("Save", callback_data=f"tx:confirm:{ledger_id}"),
                InlineKeyboardButton("Cancel", callback_data=f"tx:cancel:{ledger_id}"),
            ],
        ]
    )


def delete_keyboard(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Delete", callback_data=f"tx:delete:{ledger_id}"),
                InlineKeyboardButton("Keep", callback_data=f"tx:keep:{ledger_id}"),
            ]
        ]
    )


def success_keyboard(ledger_id: str, bank: str = "", last4: str = "") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("Done", callback_data=f"tx:done:{ledger_id}")],
    ]
    if bank and last4:
        rows.append(
            [InlineKeyboardButton("History", callback_data=f"tx:history:{bank}:{last4}")]
        )
    return InlineKeyboardMarkup(rows)


def home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Rates", callback_data="console:rates"),
                InlineKeyboardButton("Open", callback_data="console:open"),
            ]
        ]
    )
