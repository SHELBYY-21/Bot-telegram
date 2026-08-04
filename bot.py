"""CE VAULT — premium FinTech operations console (Telegram).

Supabase (or SQLite) ledger + typography-first OLED card UX.
Not a chatbot — one card per decision, edit-in-place.

Commands:
  /start /help /console  — operations home
  /rates                 — buy / sell / USDT float
  /setrates <buy> <sell> — publish desk rates
  /balance [usdt]        — show or set USDT float
  /ledger [id]           — recent entries or one card
  /history [BANK last4]  — receiver dossier
  /status [id]           — active or specific ledger
  /today                 — mini dashboard (counts, sums, profit, pending)
  /staff                 — per-person totals for today
  /demo                  — offline fixture slip
  /delete <id>           — delete confirmation

Inputs:
  • Bank slip photo (optional caption)
  • USDT amount  e.g. 12.5  or  USDT 12.5
  • Structured slip text
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from ce_vault.config import Settings
from ce_vault.handlers import (
    cmd_balance,
    cmd_delete,
    cmd_demo,
    cmd_help,
    cmd_history,
    cmd_ledger,
    cmd_rates,
    cmd_setrates,
    cmd_staff,
    cmd_start,
    cmd_status,
    cmd_today,
    on_callback,
    on_photo,
    on_text,
)
from ce_vault.session import SessionStore
from ce_vault.storage import create_slip_storage
from ce_vault.store import create_ledger

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO
)
logger = logging.getLogger("ce_vault")


async def on_shutdown(application: Application) -> None:
    for key in ("ledger", "slip_storage"):
        close = getattr(application.bot_data.get(key), "close", None)
        if callable(close):
            close()


def build_app(settings: Settings | None = None, ledger_store=None) -> Application:
    settings = settings or Settings.from_env()
    settings.images_dir.mkdir(parents=True, exist_ok=True)

    application = (
        Application.builder()
        .token(settings.telegram_token)
        .post_shutdown(on_shutdown)
        .build()
    )
    store = ledger_store or create_ledger()
    application.bot_data["settings"] = settings
    application.bot_data["ledger"] = store
    application.bot_data["slip_storage"] = create_slip_storage()
    application.bot_data["sessions"] = SessionStore(settings.state_file)

    application.add_handler(CommandHandler(["start", "console"], cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("rates", cmd_rates))
    application.add_handler(CommandHandler("setrates", cmd_setrates))
    application.add_handler(CommandHandler("balance", cmd_balance))
    application.add_handler(CommandHandler("today", cmd_today))
    application.add_handler(CommandHandler("staff", cmd_staff))
    application.add_handler(CommandHandler("ledger", cmd_ledger))
    application.add_handler(CommandHandler("history", cmd_history))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("demo", cmd_demo))
    application.add_handler(CommandHandler("delete", cmd_delete))
    application.add_handler(CallbackQueryHandler(on_callback))
    application.add_handler(MessageHandler(filters.PHOTO, on_photo))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_text)
    )
    return application


def main() -> None:
    settings = Settings.from_env()
    app = build_app(settings)
    logger.info("CE VAULT console starting (polling)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
