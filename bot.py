"""CE VAULT — Premium FinTech Operations Console.

Entry point for the Telegram bot. Run with:

    python bot.py

For the legacy Cursor Cloud Agents bot:

    LEGACY_CURSOR_BOT=1 python bot.py
"""

from __future__ import annotations

import os


def main() -> None:
    if os.environ.get("LEGACY_CURSOR_BOT", "").lower() in ("1", "true", "yes"):
        from cursor_bot import main as legacy_main
        legacy_main()
    else:
        from bot.app import main as vault_main
        vault_main()


if __name__ == "__main__":
    main()
