# CE VAULT

Premium FinTech Operations Console for Telegram — a secure ledger for THB/USDT exchange operations with OCR slip verification.

## Design

CE VAULT is built as an enterprise-grade financial operating system, not a chatbot:

- Dark, typography-first card layouts
- One card per screen, one decision per view
- Monospace for all monetary values
- Status pipeline: RECEIVED → OCR VERIFIED → WAITING USDT → SETTLED
- Inline action buttons (Confirm / Edit / Cancel)
- Message editing instead of spam

## What it does

| Input | Flow |
|---|---|
| Bank slip photo | OCR → verification card → confirmation → settle |
| USDT amount | Wait for slip → OCR → confirmation → settle |

Everything is calculated automatically. Buy rate and sell rate are configured via environment — never asked from the user.

### Commands

| Command | Description |
|---|---|
| `/start` | Console overview |
| `/balance` | Current USDT balance |
| `/rates` | Active buy/sell rates and spread |
| `/history` | Recent transactions |
| `/ledger <id>` | View a specific transaction |
| `/cancel` | Cancel pending transaction |

## Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Configure and run:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # fill in TELEGRAM_BOT_TOKEN
set -a && source .env && set +a
python bot.py
```

Set `ALLOWED_USER_IDS` in `.env` to restrict access to specific Telegram users.

### Environment

| Variable | Default | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | BotFather token (required) |
| `ALLOWED_USER_IDS` | open | Comma-separated Telegram user IDs |
| `DEFAULT_BUY_RATE` | `39.89` | Auto-applied buy rate |
| `DEFAULT_SELL_RATE` | `40.00` | Auto-applied sell rate |
| `OCR_CONFIDENCE_WARN` | `90` | Warning threshold (%) |
| `OCR_API_URL` | — | Optional external OCR endpoint |
| `DATA_DIR` | `data` | Storage directory |
| `DB_PATH` | `data/vault.db` | SQLite database path |

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Architecture

```
bot/
  app.py              # Application entry
  handlers/           # Commands, photos, callbacks, messages
  keyboards.py        # Inline keyboard builders
  messaging.py        # Send/edit card helpers
cards/
  base.py             # Header, status, typography
  confirmation.py     # Transaction card
  ocr.py              # OCR verification card
  success.py          # Settlement card
  history.py          # Receiver history card
  error.py            # Error card
services/
  ledger.py           # Transaction lifecycle
  ocr.py              # Slip OCR pipeline
  rates.py            # Rate calculations
db/
  repository.py       # SQLite data access
  schema.py           # Database schema
```

## Legacy Mode

The original Cursor Cloud Agents bot is preserved for backward compatibility:

```bash
LEGACY_CURSOR_BOT=1 python bot.py
```

Requires `CURSOR_API_KEY` in addition to `TELEGRAM_BOT_TOKEN`. See `cursor_bot.py` and `cursor_api.py`.

## Files

- `bot.py` — Entry point (CE VAULT by default)
- `bot/app.py` — CE VAULT application
- `cursor_bot.py` — Legacy Cursor Cloud Agents bot
- `cursor_api.py` — Cursor API client (legacy)
- `data/vault.db` — Ledger database (created at runtime)
