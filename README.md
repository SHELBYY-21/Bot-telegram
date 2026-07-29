# CE VAULT

Premium FinTech operations console for Telegram. Staff settle THB ↔ USDT transfers with automatic rates, OCR slip verification, and a ledger — one card per screen.

## Design

- Dark, typography-first cards (no chatbot paragraphs)
- Monospace numbers, status pipeline (`RECEIVED` → `OCR VERIFIED` → `WAITING USDT` → `SETTLED`)
- Message editing instead of message spam
- Inline **Confirm** / **Edit** / **Cancel** actions

## What staff provide

| Input | Result |
|---|---|
| Transfer slip (photo) | OCR → transaction card → settle |
| USDT amount (e.g. `12.5342`) | Auto THB + rates → transaction card → settle |

Buy rate, sell rate, profit, and ledger ID are always computed automatically.

## Commands

| Command | Action |
|---|---|
| `/start` | Operations dashboard |
| `/balance` | Volume + rate summary |
| `/ledger [id]` | View entry or recent settlements |
| `/delete <id>` | Remove a ledger entry |

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # fill in TELEGRAM_BOT_TOKEN
set -a && source .env && set +a
python bot.py
```

For real slip OCR, install [Tesseract](https://github.com/tesseract-ocr/tesseract) with Thai language data. Set `OCR_PROVIDER=tesseract` or leave `auto` (falls back to deterministic mock when Tesseract is unavailable).

Set `ALLOWED_USER_IDS` to restrict access.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Architecture

```
bot.py              Telegram handlers, callbacks, message editing
config.py           Environment helpers
vault/
  cards.py          Premium card renderer (one card per screen)
  ledger.py         SQLite ledger + receiver history
  ocr.py            Slip OCR pipeline
  rates.py          Automatic THB/USDT rate engine
  session.py        Per-chat draft state
  models.py         Domain types
cursor_api.py       Legacy Cursor Cloud Agents client (unchanged)
storage/ledger.db   Runtime ledger database (git-ignored)
```

## Ledger fields

Each settled transaction stores: Ledger ID, slip hash, OCR confidence, receiver, bank, last4, THB, USDT, buy/sell rates, profit %, staff ID, timestamps, and running balance.
