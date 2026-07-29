# CE VAULT

Premium FinTech Operations Console for Telegram. Process THB/USDT settlements from payment slips or USDT amounts — rates, profit, and ledger entries are calculated automatically.

Designed like an enterprise financial operating system: one card per screen, monospace numbers, status pipeline, and in-place message editing.

## Features

- **Slip OCR** — extract receiver, bank, last4, and THB amount with confidence scoring
- **USDT entry** — send an amount (e.g. `12.5342`) and THB is calculated automatically
- **Auto rates** — buy/sell rates and profit % from configuration; never prompted
- **Ledger** — SQLite storage for every transaction (slip hash, OCR, receiver, rates, staff, timestamps)
- **Receiver history** — transaction count, volume, first/last seen, risk level
- **Duplicate detection** — rejects already-processed slips
- **Premium cards** — Receive, OCR, Transaction, Success, History, Error, Edit, Delete layouts

## Status pipeline

```
○ RECEIVED
○ OCR VERIFIED
● WAITING USDT    ← only the active step is highlighted
○ SETTLED
```

## Commands

| Command | Description |
|---|---|
| `/start` | Open the operations console |
| `/balance` | Settled THB and USDT totals |
| `/ledger` | Recent ledger entries |

## Input

| Input | Result |
|---|---|
| Payment slip image | OCR → confirmation card → settle |
| `12.5342` or `12.5342 usdt` | USDT amount → confirmation card |
| `500` or `500 thb` | THB amount → confirmation card |

Buttons on the confirmation card: **Confirm**, **Edit**, **Cancel**.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # set TELEGRAM_BOT_TOKEN
set -a && source .env && set +a
python bot.py
```

Set `ALLOWED_USER_IDS` to restrict access. Leave empty to allow anyone with the bot link.

### OCR providers

| Provider | Config | Notes |
|---|---|---|
| `mock` (default) | `OCR_PROVIDER=mock` | Deterministic demo OCR from image hash |
| Google Vision | `OCR_PROVIDER=vision` + `GOOGLE_VISION_API_KEY` | Production OCR |

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Architecture

```
bot.py              Telegram handlers, callbacks, message editing
config.py           Environment settings
db/                 SQLite ledger + receiver history
services/           OCR, rates, transaction orchestration
ui/                 Premium card renderers and session state
cursor_api.py       Legacy Cursor Cloud Agents client (unchanged)
```

## Design tokens

| Token | Value |
|---|---|
| Primary | `#05050A` |
| Surface | `#101114` |
| Accent Gold | `#E5C04A` |
| Accent Cyan | `#00F0FF` |
| Success | `#00D26A` |
| Warning | `#FFB800` |
| Danger | `#FF4D4F` |

Telegram renders structured HTML (`<code>` for monospace numbers, bold status pipeline). Colors are reference tokens for future web surfaces.
