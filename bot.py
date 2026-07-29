"""CE VAULT — Premium FinTech Operations Console.

Telegram surface for THB↔USDT settlement:
  slip image  OR  USDT amount  →  OCR / quote  →  Confirm · Edit · Cancel

Backward compatible:
  - `cursor_api.py` remains available
  - Optional Cursor Cloud Agent commands when ENABLE_CURSOR_AGENTS=1
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
    cmd_delete,
    cmd_help,
    cmd_history,
    cmd_ledger,
    cmd_open,
    cmd_rates,
    cmd_sell,
    cmd_start,
    on_callback,
    on_photo,
    on_text,
)
from ce_vault.ledger import LedgerStore
from ce_vault.rates import RateService

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO
)
logger = logging.getLogger("bot")

# Re-exports used by tests / external tooling
from ce_vault.handlers.console import allowed_user_ids, authorized  # noqa: E402

STATE_FILE = Path(os.environ.get("STATE_FILE", "state.json"))


def load_state() -> dict:
    """Legacy chat-settings JSON (Cursor agents mode)."""
    import json

    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            logger.warning("state file corrupt, starting fresh")
    return {}


def save_state(state: dict) -> None:
    import json

    STATE_FILE.write_text(json.dumps(state, indent=2))


def chat_settings(state: dict, chat_id: int) -> dict:
    return state.setdefault(str(chat_id), {})


def _register_cursor_agents(application: Application) -> None:
    """Optional legacy Cursor Cloud Agents commands."""
    from cursor_api import CursorClient
    import agents_bridge

    api_key = os.environ.get("CURSOR_API_KEY")
    if not api_key:
        logger.warning("ENABLE_CURSOR_AGENTS=1 but CURSOR_API_KEY missing — skipping")
        return

    application.bot_data["cursor"] = CursorClient(api_key)
    application.bot_data["state"] = load_state()
    agents_bridge.register(application)
    logger.info("Cursor Cloud Agents bridge enabled")


async def on_shutdown(application: Application) -> None:
    client = application.bot_data.get("cursor")
    if client is not None:
        await client.close()


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN must be set")

    application = (
        Application.builder().token(token).post_shutdown(on_shutdown).build()
    )

    db_path = os.environ.get("LEDGER_DB", "ledger.db")
    ledger = LedgerStore(db_path)
    application.bot_data["ledger"] = ledger
    application.bot_data["rates"] = RateService(ledger)

    # CE VAULT console
    vault_commands = {
        "start": cmd_start,
        "help": cmd_help,
        "rates": cmd_rates,
        "sell": cmd_sell,
        "balance": cmd_balance,
        "open": cmd_open,
        "ledger": cmd_ledger,
        "history": cmd_history,
        "delete": cmd_delete,
    }
    for name, fn in vault_commands.items():
        application.add_handler(CommandHandler(name, fn))

    application.add_handler(CallbackQueryHandler(on_callback))
    application.add_handler(MessageHandler(filters.PHOTO, on_photo))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_text)
    )

    if os.environ.get("ENABLE_CURSOR_AGENTS", "").lower() in ("1", "true", "yes"):
        _register_cursor_agents(application)

    logger.info("CE VAULT console starting (polling)")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
