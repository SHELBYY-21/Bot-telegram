# CE VAULT

Premium FinTech Operations Console on Telegram — THB ↔ USDT settlement with OCR, ledger, and automatic rates.

Not a chatbot. One card. One decision. Terminal-grade UX.

## Console

| Input | Result |
|---|---|
| Bank slip photo (+ optional caption) | OCR card → Confirmation card |
| Slip text | OCR card → Confirmation card |
| USDT amount (`12.5342`) | Confirmation card |

Staff never enters Buy Rate. System calculates USDT, profit, and balance.

### Status rail

```
● RECEIVED
● OCR VERIFIED
● WAITING USDT
● SETTLED
```

Only the active step glows.

### Cards

Receive · OCR · Confirmation · Success · History · Error · Edit · Delete

Each message is a single card. Previous console messages are edited in place.

## Commands

| Command | Action |
|---|---|
| `/start` | Operations console |
| `/rates` | Buy / Sell / Profit desk |
| `/sell <rate>` | Update Sell Rate only |
| `/balance` | Treasury balance |
| `/open` | Open (WAITING USDT) entries |
| `/ledger <id>` | Open a ledger card |
| `/history <bank> <last4>` | Receiver history |
| `/delete <id>` | Delete confirmation |
| `/help` | Compact help |

Buttons on cards: **Confirm · Edit · Cancel**

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # set TELEGRAM_BOT_TOKEN
set -a && source .env && set +a
python bot.py
```

Optional: set `OPENAI_API_KEY` for Vision OCR on slip images. Without it, caption/text parsing is used.

Set `ALLOWED_USER_IDS` to lock the console to staff Telegram IDs.

## Architecture

```
bot.py                 entrypoint
ce_vault/
  theme.py             typography + money formatting
  ui/                  cards · status · keyboards
  ledger/              SQLite secure ledger
  ocr/                 slip vision + duplicate detection
  rates/               automatic quote engine
  handlers/            Telegram console UX
cursor_api.py          legacy Cursor Agents client (optional)
agents_bridge.py       optional agent commands when ENABLE_CURSOR_AGENTS=1
```

### Ledger fields

Ledger ID · Slip · OCR · Receiver · Bank · Last4 · THB · USDT · Buy Rate · Sell Rate · Profit · Staff · Timestamp · History · Images

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Legacy Cursor Agents

The previous Cloud Agents bot remains available behind `ENABLE_CURSOR_AGENTS=true` and `CURSOR_API_KEY`. Agent delete is `/adelete` so it does not clash with CE VAULT `/delete`.
