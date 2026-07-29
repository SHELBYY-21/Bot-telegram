"""CE VAULT — Premium FinTech Operations Console."""

from __future__ import annotations

import logging
import os

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot.auth import authorized
from bot.handlers.callbacks import handle_callback
from bot.handlers.commands import (
    cmd_balance,
    cmd_cancel,
    cmd_help,
    cmd_history,
    cmd_ledger,
    cmd_rates,
    cmd_start,
)
from bot.handlers.messages import handle_text
from bot.handlers.photos import handle_document, handle_photo
from config import DATA_DIR, SLIPS_DIR, TELEGRAM_BOT_TOKEN
from db.repository import get_repository
from services.ledger import LedgerService

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("vault")


def build_application(token: str | None = None) -> Application:
    """Build and configure the CE VAULT application."""
    bot_token = token or TELEGRAM_BOT_TOKEN or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN must be set")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SLIPS_DIR.mkdir(parents=True, exist_ok=True)

    application = Application.builder().token(bot_token).build()

    repo = get_repository()
    application.bot_data["repo"] = repo
    application.bot_data["ledger"] = LedgerService(repo)

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("balance", cmd_balance))
    application.add_handler(CommandHandler("rates", cmd_rates))
    application.add_handler(CommandHandler("history", cmd_history))
    application.add_handler(CommandHandler("ledger", cmd_ledger))
    application.add_handler(CommandHandler("cancel", cmd_cancel))

    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.IMAGE, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return application


def main() -> None:
    application = build_application()
    logger.info("CE VAULT starting")
    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
