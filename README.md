# CE Vault — FinTech Operations Console

Premium Telegram operations desk for THB ↔ USDT settlement.
**Not a chatbot.** One screen = one decision. Cards, not paragraphs.

## Design

Dark OLED console language: typography-first cards, monospace money,
status rail (`RECEIVED → OCR VERIFIED → WAITING USDT → SETTLED`),
edit-in-place messages, inline Confirm / Edit / Cancel.

## Operator flow

1. Send a **slip photo** (or paste slip text) — OR — send a **USDT amount**
2. Console runs OCR, applies desk buy/sell rates automatically
3. Confirm → Waiting USDT → Mark Settled
4. Ledger stores slip, OCR, receiver, rates, profit, staff, timestamps

Never asked for buy rate during intake. Set desk rates with `/rates`.

## Commands

| Command | Action |
|---|---|
| `/start` `/console` | Desk home — rates + open queue |
| `/rates [buy] [sell]` | Show or update desk FX |
| `/ledger <id>` | Open one ledger card |
| `/history <bank> <last4>` | Receiver history card |
| `/open` | Newest open ledger |
| `/delete <id>` | Delete confirmation card |

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # TELEGRAM_BOT_TOKEN required
set -a && source .env && set +a
python bot.py
```

Optional: set `OPENAI_API_KEY` for Vision OCR on slip images.
Without it, attach a caption or paste slip text (`THB`, bank, account).

## Architecture

```
bot.py                 entrypoint
ce_vault/
  cards.py             one-card renderers
  theme.py             typography + monospace money
  status.py            pipeline rail
  rates.py             FX + profit
  ocr.py               vision / heuristic OCR
  ledger.py            SQLite ledger + receiver memory
  engine.py            desk orchestration
  handlers.py          Telegram wiring
  ui.py                edit-in-place + keyboards
  config.py            env settings
```

`cursor_api.py` remains for legacy Cursor Cloud Agents integrations; the console no longer depends on it.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```
