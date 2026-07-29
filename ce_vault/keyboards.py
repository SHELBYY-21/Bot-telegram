"""Inline keyboards — one decision per screen."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def confirm_edit_cancel(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Confirm", callback_data=f"lv:confirm:{ledger_id}"),
                InlineKeyboardButton("Edit", callback_data=f"lv:edit:{ledger_id}"),
                InlineKeyboardButton("Cancel", callback_data=f"lv:cancel:{ledger_id}"),
            ]
        ]
    )


def settle_waiting(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Mark Settled", callback_data=f"lv:settle:{ledger_id}"),
                InlineKeyboardButton("Cancel", callback_data=f"lv:cancel:{ledger_id}"),
            ]
        ]
    )


def delete_confirm(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Delete", callback_data=f"lv:delete:{ledger_id}"),
                InlineKeyboardButton("Keep", callback_data=f"lv:keep:{ledger_id}"),
            ]
        ]
    )


def edit_fields(ledger_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("THB", callback_data=f"lv:editfield:{ledger_id}:thb"),
                InlineKeyboardButton("Receiver", callback_data=f"lv:editfield:{ledger_id}:receiver"),
            ],
            [
                InlineKeyboardButton("Bank", callback_data=f"lv:editfield:{ledger_id}:bank"),
                InlineKeyboardButton("Last4", callback_data=f"lv:editfield:{ledger_id}:last4"),
            ],
            [
                InlineKeyboardButton("Back", callback_data=f"lv:back:{ledger_id}"),
            ],
        ]
    )


def agent_actions(agent_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Status", callback_data=f"ag:status:{agent_id}"),
                InlineKeyboardButton("Stop", callback_data=f"ag:stop:{agent_id}"),
            ]
        ]
    )


def done_only() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Done", callback_data="lv:dismiss")]]
    )
