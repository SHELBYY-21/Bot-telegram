"""CE VAULT — Premium FinTech Operations Console (Telegram).

Dark OLED card UI. One screen = one decision.
Slip image or USDT amount in → settled ledger out.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from ce_vault.handlers import (
    cmd_balance,
    cmd_console,
    cmd_help,
    cmd_history,
    cmd_ledger,
    cmd_rates,
    cmd_setbalance,
    cmd_start,
    on_callback,
    on_photo,
    on_text,
)
from ce_vault.ledger import Ledger

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO
)
logger = logging.getLogger("ce_vault")

# Re-export auth helpers for tests / backward-compatible imports
from ce_vault.handlers import allowed_user_ids, authorized  # noqa: E402


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN must be set")

    db_path = Path(os.environ.get("LEDGER_DB", "ce_vault.db"))
    application = Application.builder().token(token).build()
    application.bot_data["ledger"] = Ledger(db_path)

    application.add_handler(CommandHandler(["start", "console"], cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("rates", cmd_rates))
    application.add_handler(CommandHandler("balance", cmd_balance))
    application.add_handler(CommandHandler("setbalance", cmd_setbalance))
    application.add_handler(CommandHandler("ledger", cmd_ledger))
    application.add_handler(CommandHandler("history", cmd_history))
    application.add_handler(CallbackQueryHandler(on_callback))
    application.add_handler(MessageHandler(filters.PHOTO, on_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    # Optional: keep Cursor Cloud Agents module available when enabled
    if os.environ.get("ENABLE_CURSOR_AGENTS", "").lower() in ("1", "true", "yes"):
        _mount_cursor_agents(application)

    logger.info("CE VAULT console starting (polling)")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


def _mount_cursor_agents(application: Application) -> None:
    """Backward-compatible Cursor Cloud Agents commands (opt-in)."""
    from cursor_api import CursorClient
    import bot_agents as agents

    api_key = os.environ.get("CURSOR_API_KEY")
    if not api_key:
        logger.warning("ENABLE_CURSOR_AGENTS set but CURSOR_API_KEY missing — skipped")
        return
    application.bot_data["cursor"] = CursorClient(api_key)
    application.bot_data["state"] = agents.load_state()
    agents.register(application)
    logger.info("Cursor Cloud Agents commands mounted")


if __name__ == "__main__":
    main()
