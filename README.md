# CE VAULT

Premium FinTech Operations Console for Telegram — OLED, typography-first, one card per decision.

Not a chatbot UI. Operates like a Bloomberg / Stripe / Linear console inside Telegram.

## Operations

| Action | Input |
|---|---|
| Slip intake | Send a transfer slip photo (caption optional) |
| USDT intake | `/usdt <amount>` |
| Rate board | `/rates` |
| Lookup | `/ledger <id>` |
| Receiver history | `/history <last4>` |
| Latest entry | `/recent` |
| Void | `/void <id>` |

Staff never enters Buy Rate. Everything is calculated from `SELL_RATE` + `RATE_SPREAD`.

### Status rail

```
● RECEIVED
● OCR VERIFIED
● WAITING USDT
○ SETTLED
```

Only the active step is emphasized. Cards edit in place — no message spam.

### Cards

Receive · OCR · Confirmation · Success · History · Error · Edit · Delete

Each response is a single card.

## Architecture

```
bot.py                 Telegram wiring + Cursor agent commands
ce_vault/
  design.py            Palette + status vocabulary
  cards.py             Single-purpose HTML card renderers
  rates.py             Automatic buy/sell/USDT quotes
  ocr.py               Vision / caption slip intake
  ledger.py            SQLite ledger + receiver history
  keyboards.py         Confirm / Edit / Cancel
  messaging.py         Edit-in-place + typing
  handlers.py          FinTech command + callback flows
cursor_api.py          Cursor Cloud Agents client (backward compatible)
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # fill TELEGRAM_BOT_TOKEN
set -a && source .env && set +a
python bot.py
```

Optional:

- `OPENAI_API_KEY` — vision OCR for slips (otherwise caption/heuristic)
- `CURSOR_API_KEY` — enables `/agent` cloud-agent commands
- `ALLOWED_USER_IDS` — lock the console to staff Telegram IDs

## Cursor Agents (compat)

Existing commands still work, restyled into CE VAULT cards:

`/repo` `/model` `/models` `/repos` `/agent` `/agents` `/status` `/conversation` `/followup` `/stop` `/delete` `/me`

Status updates edit the same message instead of flooding the chat.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Ledger schema

Each entry stores: Ledger ID, slip hash, OCR payload, receiver, bank, last4, THB, USDT, buy/sell rates, profit, confidence, staff, timestamps, and an event history.
