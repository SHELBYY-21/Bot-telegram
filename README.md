"""CE VAULT — Premium FinTech Operations Console for Telegram.

Not a chatbot. A Bloomberg / Stripe / Linear-grade operations surface for
THB ↔ USDT settlement, slip OCR, and ledger control.

## What it does

| Input | Result |
|---|---|
| Slip photo | OCR → confirmation card (Confirm / Edit / Cancel) |
| USDT amount | Auto-quoted receive card |
| Confirm | Settle ledger · update vault balance · success card |

Buy Rate is **never** requested. Rates come from `BUY_RATE` / `SELL_RATE`.

### Commands

| Command | Action |
|---|---|
| `/start` `/console` | Operations home |
| `/rates` | Live Buy / Sell / Profit |
| `/balance` | Vault balance |
| `/history SCB 3376` | Receiver history card |
| `/ledger LV-…` | Re-open a ledger card |

### Cards (one per message)

Receive · OCR · Confirmation · Success · History · Error · Edit · Delete

Status pipeline (single glow):

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

Optional: set `OPENAI_API_KEY` for Vision OCR on slip photos. Without it, the
console uses caption text + heuristic parsing and routes low-confidence slips
to Edit.

Set `ALLOWED_USER_IDS` to lock the console to staff accounts.

## Architecture

```
bot.py                 Telegram handlers (thin)
ce_vault/
  cards.py             OLED card renderers
  theme.py             Status pipeline + design tokens
  ledger.py            SQLite ledger + receiver history
  rates.py             Automatic FX quotes
  ocr.py               Slip vision / heuristic OCR
  flow.py              Transaction assembly
  messaging.py         Edit-in-place + typing
  keyboards.py         Decision buttons
cursor_api.py          Legacy Cloud Agents client (unchanged, still importable)
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Ledger fields

Ledger ID · Slip · OCR · Receiver · Bank · Last4 · THB · USDT · Buy Rate ·
Sell Rate · Profit · Staff · Timestamp · History · Images
