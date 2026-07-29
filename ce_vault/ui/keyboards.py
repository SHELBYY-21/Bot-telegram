"""Inline keyboards — one decision cluster per card."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def kb_confirm(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Confirm", callback_data=f"cf:{ledger_id}"),
                InlineKeyboardButton("Edit", callback_data=f"ed:{ledger_id}"),
                InlineKeyboardButton("Cancel", callback_data=f"cx:{ledger_id}"),
            ]
        ]
    )


def kb_ocr_next(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Continue", callback_data=f"oc:{ledger_id}"),
                InlineKeyboardButton("Cancel", callback_data=f"cx:{ledger_id}"),
            ]
        ]
    )


def kb_delete(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Delete", callback_data=f"dl:{ledger_id}"),
                InlineKeyboardButton("Keep", callback_data=f"kp:{ledger_id}"),
            ]
        ]
    )


def kb_edit(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Cancel Edit", callback_data=f"cx:{ledger_id}")]]
    )


def kb_done(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("History", callback_data=f"hs:{ledger_id}"),
                InlineKeyboardButton("New", callback_data="nw"),
            ]
        ]
    )


def kb_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Open", callback_data="ls:open"),
                InlineKeyboardButton("Settled", callback_data="ls:settled"),
                InlineKeyboardButton("Rates", callback_data="rt"),
            ]
        ]
    )
