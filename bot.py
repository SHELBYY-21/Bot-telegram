"""CE Vault — FinTech Operations Console (Telegram).

Not a chatbot. One card. One decision.
"""

from __future__ import annotations

import logging

from telegram.ext import Application

from ce_vault.config import load_settings
from ce_vault.engine import DeskState
from ce_vault.handlers import build_handlers
from ce_vault.ledger import LedgerStore
from ce_vault.rates import RateBook

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("ce_vault")


def build_application() -> Application:
    cfg = load_settings()
    store = LedgerStore(cfg.db_path)

    buy = store.get_meta("buy_rate")
    sell = store.get_meta("sell_rate")
    rates = RateBook.from_floats(
        float(buy) if buy else cfg.buy_rate,
        float(sell) if sell else cfg.sell_rate,
    )
    # Persist defaults so desk survives restarts
    store.set_meta("buy_rate", str(rates.buy_rate))
    store.set_meta("sell_rate", str(rates.sell_rate))

    desk = DeskState(
        store=store,
        rates=rates,
        ocr_api_key=cfg.openai_api_key,
        ocr_model=cfg.ocr_model,
        ocr_warn_below=cfg.ocr_warn_below,
    )

    application = Application.builder().token(cfg.telegram_token).build()
    application.bot_data["settings"] = cfg
    application.bot_data["desk"] = desk

    for handler in build_handlers():
        application.add_handler(handler)

    return application


def main() -> None:
    app = build_application()
    logger.info("CE Vault console starting")
    app.run_polling()


if __name__ == "__main__":
    main()
