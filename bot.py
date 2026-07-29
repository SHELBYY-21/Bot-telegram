"""CE VAULT — Premium FinTech Operations Console.

Entry point (backward compatible):
  python bot.py

Commands:
  /start /console   — operations console home
  /rates [buy sell] — view or set desk rates
  /history [BANK LAST4] — counterparty dossier
  /ledger <id>      — open a ledger card
  /balance          — treasury USDT balance

Intake:
  • Bank slip photo → OCR → Confirm → Settle
  • `12.5 USDT` → auto-quote → Confirm → Settle
"""

from __future__ import annotations

from ce_vault.app import main
from ce_vault.compat import (  # noqa: F401
    STATE_FILE,
    allowed_user_ids,
    chat_settings,
    load_state,
    save_state,
)

if __name__ == "__main__":
    main()
