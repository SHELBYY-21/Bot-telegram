"""Inline keyboards — one decision per card."""

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


def delete_keyboard(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Void", callback_data=f"void:{ledger_id}"),
                InlineKeyboardButton("Keep", callback_data=f"keep:{ledger_id}"),
            ]
        ]
    )


def ocr_keyboard(ledger_id: str, *, warn: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("Continue", callback_data=f"ocr_ok:{ledger_id}"),
            InlineKeyboardButton("Edit", callback_data=f"edit:{ledger_id}"),
        ]
    ]
    if warn:
        rows.append(
            [InlineKeyboardButton("Cancel", callback_data=f"cancel:{ledger_id}")]
        )
    return InlineKeyboardMarkup(rows)


def done_keyboard(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("History", callback_data=f"history:{ledger_id}"),
                InlineKeyboardButton("New", callback_data="new"),
            ]
        ]
    )


def home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Rates", callback_data="rates"),
                InlineKeyboardButton("Open", callback_data="open"),
            ]
        ]
    )
