# Bot-telegram → CE VAULT

Premium FinTech Operations Console on Telegram.

Not a chatbot. A dark OLED ledger terminal for THB → USDT desk operations:
slip ingest, OCR verification, automatic rate math, settlement, and receiver history.

## Operator flow

1. Send a **bank slip image** (or paste slip text), **or** type a **USDT amount**
2. Console runs Vision / parse → shows **OCR card** → **Confirmation card**
3. **Confirm** → Waiting USDT → **Mark Settled** → **Success card**
4. Edit / Cancel / Delete as needed — one card per screen, messages edit in place

Buy rate is never requested during a transaction. The rate desk publishes once via `/setrates`.

## Commands

| Command | Purpose |
|---|---|
| `/start` | Console home |
| `/demo` | Offline fixture slip (no image needed) |
| `/rates` | Rate desk + USDT balance |
| `/setrates <buy> <sell>` | Publish desk rates |
| `/balance [usdt]` | Show or set USDT float |
| `/history [BANK last4]` | Receiver dossier |
| `/ledger [id]` | Recent entries or one ledger card |
| `/delete <id>` | Delete confirmation |

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # fill TELEGRAM_BOT_TOKEN
set -a && source .env && set +a
python bot.py
```

Set `ALLOWED_USER_IDS` to lock the console to staff Telegram IDs.

Optional: set `OCR_API_KEY` (or `OPENAI_API_KEY`) for Vision OCR on slip photos. Without it, the console parses captions / pasted slip text.

## Architecture

```
bot.py                 Telegram console (edit-in-place UX)
vault/
  cards.py             One-card renderers (Receive, OCR, Success, History, Error, Edit, Delete)
  theme.py             Status pipeline + design tokens
  formatting.py        Monospace money / crypto helpers
  keyboards.py         Confirm / Edit / Settle actions
  ledger.py            SQLite WAL ledger + receiver history
  rates.py             Auto USDT + profit from desk rates
  ocr.py               Slip parse + optional Vision API
cursor_api.py          Legacy Cursor Cloud Agents client (backward compatible)
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Design language

- Dark OLED hierarchy, typography-first
- Monospace for every number
- Status rail: `● RECEIVED` → `● OCR VERIFIED` → `● WAITING USDT` → `● SETTLED` (one glow)
- Never spam — edit the previous console message whenever possible
