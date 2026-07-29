# CE VAULT — Premium FinTech Operations Console

Telegram operations console for THB ↔ USDT settlement.
Designed like a Bloomberg / Stripe / Linear terminal — not a chatbot.

## Console

Every response is **one card**. One screen = one decision.

| Card | Purpose |
|---|---|
| Receive | Inbound slip captured |
| OCR | Vision result + confidence |
| Confirmation | Quote ready — Confirm / Edit / Cancel |
| Success | Settled + updated balance |
| History | Receiver risk profile |
| Error | Problem · Cause · Action |
| Edit / Delete | Mutation surfaces |

### Staff inputs

- Slip image (or pasted slip text)
- **or** an amount: `500` / `12.5 usdt`

Everything else is automatic (buy rate, sell rate, USDT, profit).

### Commands

| Command | Action |
|---|---|
| `/start` | Console help |
| `/rates` | Active buy/sell spread |
| `/setrates <buy> <sell>` | Update global rates |
| `/balance` | USDT inventory / THB collected |
| `/setbalance <usdt> [thb]` | Set inventory |
| `/history <last4>` | Receiver history card |
| `/ledger <id>` | Open a ledger entry |
| `/recent` | Latest ledger strip |

### Status rail

```
● RECEIVED
○ OCR VERIFIED
○ WAITING USDT
○ SETTLED
```

Only the active step glows.

## Architecture

```
bot.py              Telegram console (edit-in-place cards)
vault/
  design.py         OLED tokens, status rail, monospace money
  cards.py          Single-card renderers
  ledger.py         SQLite ledger + balance + receiver history
  rates.py          Automatic quote engine
  ocr.py            Slip OCR (Vision API or heuristics)
  models.py         Transaction / OCR domain models
  console.py        Message edit + inline keyboards
cursor_api.py       Optional Cursor Cloud Agents client (legacy)
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # set TELEGRAM_BOT_TOKEN
set -a && source .env && set +a
python bot.py
```

Optional:

- `OPENAI_API_KEY` — Vision OCR for slip photos
- `CURSOR_API_KEY` — keeps legacy `/agent` Cloud Agents commands

Set `ALLOWED_USER_IDS` to restrict operators.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Design tokens

| Token | Value |
|---|---|
| Primary | `#05050A` |
| Surface | `#101114` |
| Border | `rgba(255,255,255,.06)` |
| Gold | `#E5C04A` |
| Cyan | `#00F0FF` |
| Success | `#00D26A` |
| Warning | `#FFB800` |
| Danger | `#FF4D4F` |
