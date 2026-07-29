"""CE VAULT — premium FinTech operations console (Telegram).

Not a chatbot. An operations surface for slip intake, OCR verification,
automatic THB↔USDT quoting, and ledger settlement.

Commands:
  /start /help     — open console
  /rates           — show live buy/sell + vault balances
  /ledger          — recent ledger entries
  /history [BANK] [last4] — receiver history card
  /status [id]     — active or specific ledger card
  /delete <id>     — delete confirmation

Inputs (no command required):
  • Bank slip photo (optional caption)
  • USDT amount text  e.g. 12.5  or  USDT 12.5
  • Structured slip text (THB / BANK / name)
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
    cmd_delete,
    cmd_help,
    cmd_history,
    cmd_ledger,
    cmd_rates,
    cmd_start,
    cmd_status,
    on_callback,
    on_photo,
    on_text,
)
from ce_vault.ledger import Ledger
from ce_vault.ocr import OcrService
from ce_vault.rates import RateEngine
from ce_vault.session import SessionStore

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO
)
logger = logging.getLogger("ce_vault")


async def on_shutdown(application: Application) -> None:
    ocr: OcrService = application.bot_data["ocr"]
    await ocr.close()


def build_app(settings: Settings | None = None) -> Application:
    settings = settings or Settings.from_env()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.images_dir.mkdir(parents=True, exist_ok=True)

    application = (
        Application.builder()
        .token(settings.telegram_token)
        .post_shutdown(on_shutdown)
        .build()
    )
    application.bot_data["settings"] = settings
    application.bot_data["ledger"] = Ledger(settings.db_path)
    application.bot_data["rates"] = RateEngine(settings.buy_rate, settings.sell_rate)
    application.bot_data["sessions"] = SessionStore(settings.state_file)
    application.bot_data["ocr"] = OcrService(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_vision_model,
        warn_below=settings.ocr_warn_below,
    )

    application.add_handler(CommandHandler(["start", "console"], cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("rates", cmd_rates))
    application.add_handler(CommandHandler("ledger", cmd_ledger))
    application.add_handler(CommandHandler("history", cmd_history))
    application.add_handler(CommandHandler("status", cmd_status))
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
