# CE VAULT

Premium FinTech operations console on Telegram — slip intake, OCR verification, automatic THB↔USDT quoting, and ledger settlement.

Designed as a Bloomberg / Stripe / Linear-grade ops surface, not a chatbot.

## Console

| Input | Result |
|---|---|
| Bank slip photo | Vision OCR → confirmation card |
| `12.5` or `USDT 12.5` | Auto quote at sell rate |
| Structured text (`THB 500`, `BANK SCB 3376`) | Parsed intake |

| Command | Card |
|---|---|
| `/start` | Operations console |
| `/rates` | Buy / sell / vault balances |
| `/ledger` | Recent entries |
| `/history SCB 3376` | Receiver history + risk |
| `/status [id]` | Active ledger card |
| `/delete <id>` | Delete confirmation |

Rates are never asked. Staff only provide a **slip** or a **USDT amount**.

## Cards

Every message is a single card: Receive · OCR · Confirmation · Success · History · Error · Edit · Delete.

Status rail (one active glow):

```
● RECEIVED
○ OCR VERIFIED
○ WAITING USDT
○ SETTLED
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # fill TELEGRAM_BOT_TOKEN, rates
set -a && source .env && set +a
python bot.py
```

Optional: set `OPENAI_API_KEY` for Vision OCR on slip photos. Without it, paste slip text or send USDT amounts.

## Architecture

```
bot.py                 entrypoint
ce_vault/
  cards.py             typography-first card renderers
  console.py           edit-in-place message surface
  handlers.py          Telegram command / media / callback flow
  ledger.py            SQLite ledger + receiver aggregates
  rates.py             buy/sell/profit engine
  ocr.py               vision + heuristic extraction
  status.py            pipeline rail
  session.py           per-chat console state
  keyboards.py         one-decision inline actions
cursor_api.py          legacy Cursor Agents client (unchanged)
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Ledger fields

Ledger ID · Slip hash · OCR · Receiver · Bank · Last4 · THB · USDT · Buy Rate · Sell Rate · Profit · Staff · Timestamps · History · Images
