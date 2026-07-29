# CE VAULT

Telegram **FinTech Operations Console** — not a chatbot.

Dark OLED cards. One screen = one decision. Slip in → settled ledger out.

## Design language

- Typography-first hierarchy (labels small, numbers large / monospace)
- Single glowing status in the pipeline: `RECEIVED → OCR VERIFIED → WAITING USDT → SETTLED`
- One card per message — edit-in-place, never spam
- Cards: Receive · OCR · Confirmation · Success · History · Error · Edit · Delete

## Operator flow

1. Send a **bank slip photo** (caption optional) **or** type a **USDT amount**
2. Vision card shows confidence, receiver, bank, last4, amount
3. Confirmation card auto-fills THB / USDT / Buy / Sell / Profit — never ask for buy rate
4. **Confirm** · **Edit** · **Cancel**

Warnings fire when OCR confidence &lt; 90%, duplicate slips are detected, or a receiver repeats.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # TELEGRAM_BOT_TOKEN, BUY_RATE, SELL_RATE
set -a && source .env && set +a
python bot.py
```

Set `ALLOWED_USER_IDS` to lock the console to staff Telegram IDs.

### OCR providers (optional)

| Env | Provider |
|---|---|
| `EASYSLIP_TOKEN` | [EasySlip](https://easyslip.com) verify API |
| `OPENAI_API_KEY` | Vision model extraction |
| _(none)_ | Deterministic mock OCR + caption parser (offline / demo) |

## Commands

| Command | Card |
|---|---|
| `/console` `/start` | Operations home |
| `/rates` | Live buy / sell / spread |
| `/balance` | Vault USDT |
| `/setbalance <n>` | Seed vault balance |
| `/ledger <id>` | Open ledger card |
| `/history <bank> <last4>` | Receiver history |

## Architecture

```
bot.py                 entrypoint
ce_vault/
  cards.py             single-card HTML renderers
  handlers.py          intake + callbacks
  ledger.py            SQLite ledger (WAL, indexed)
  rates.py             automatic quote engine
  ocr.py               pluggable vision pipeline
  messaging.py         edit-in-place UX
  keyboards.py         Confirm / Edit / Cancel
cursor_api.py          legacy Cursor Agents client (opt-in)
bot_agents.py          legacy agent commands (ENABLE_CURSOR_AGENTS=true)
```

## Ledger fields

Ledger ID · Slip · OCR · Receiver · Bank · Last4 · THB · USDT · Buy Rate · Sell Rate · Profit · Staff · Timestamp · History · Images

## Tests

```bash
pip install -r requirements-dev.txt
PYTHONPATH=. pytest -q
```

## Backward compatibility

`cursor_api.py` and agent commands remain available. Set `ENABLE_CURSOR_AGENTS=true` and `CURSOR_API_KEY` to mount `/agent`, `/status`, etc. alongside the vault console.
