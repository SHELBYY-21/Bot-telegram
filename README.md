# CE VAULT — FinTech Operations Console (Telegram)

Premium THB ↔ USDT desk console. Not a chatbot — card-first, edit-in-place, automatic quoting.

## Console

| Action | Input |
|---|---|
| Intake slip | Send bank transfer photo (caption optional) |
| Intake USDT | `12.5342 USDT` |
| Desk rates | `/rates` or `/rates 39.89 40.00` |
| Counterparty | `/history SCB 3376` |
| Open ledger | `/ledger LD-…` |
| Treasury | `/balance` |
| Home | `/start` `/console` |

### Pipeline

`RECEIVED → OCR VERIFIED → WAITING USDT → SETTLED`

Only the active stage glows. One card per message. Confirm / Edit / Cancel on the decision screen.

### Automatic quoting

- Buy rate is **never** requested mid-flow.
- THB from slip → USDT = THB ÷ Buy Rate
- USDT amount input → THB = USDT × Buy Rate
- Profit % from Buy/Sell spread

### OCR

- `OCR_PROVIDER=auto` uses OpenAI Vision when `OPENAI_API_KEY` is set, otherwise heuristic parse of caption/text.
- Confidence below 90% triggers a review alert.
- Duplicate slips (SHA-256) and repeated receivers are flagged.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill TELEGRAM_BOT_TOKEN
set -a && source .env && set +a
python bot.py
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Layout

```
bot.py                 # entry point
ce_vault/
  app.py               # handlers + lifecycle
  config.py            # settings + design tokens
  models.py            # ledger domain
  messaging.py         # edit-in-place cards
  db/                  # SQLite ledger
  services/            # rates, OCR, ledger orchestration
  ui/                  # cards, status rail, keyboards
cursor_api.py          # legacy Cursor Agents client (optional)
```

## Ledger fields

Ledger ID · Slip · OCR · Receiver · Bank · Last4 · THB · USDT · Buy Rate · Sell Rate · Profit · Staff · Timestamp · Images · History
