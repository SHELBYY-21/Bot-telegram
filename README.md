# CE VAULT

Premium FinTech operations console on Telegram — slip intake, OCR verification, automatic THB↔USDT quoting, and ledger settlement.

Not a chatbot. A dark OLED ledger terminal: one card per decision, edit-in-place.

## Quick start

1. **Bot token** — https://t.me/BotFather  
2. **Supabase keys** (optional) — https://supabase.com/dashboard/project/cewntchvtnuyxvekivwk/settings/api  
3. **Run**

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
set -a && source .env && set +a
python bot.py
```

Without Supabase secret keys the console falls back to SQLite (`data/vault.db`).

Try `/demo` in chat for an offline fixture slip.

## Operator flow

1. Send a **bank slip image** (or paste slip text), **or** type a **USDT amount**
2. OCR card → Continue → Confirmation card
3. **Confirm** → Waiting USDT → **Mark Settled** → Success card
4. Edit / Cancel / Delete as needed

Buy rate is never requested during a transaction. Publish once via `/setrates`.

## Commands

| Command | Purpose |
|---|---|
| `/start` | Console home |
| `/demo` | Offline fixture slip |
| `/rates` | Rate desk + USDT float |
| `/setrates <buy> <sell>` | Publish desk rates |
| `/balance [usdt]` | Show or set USDT float |
| `/history [BANK last4]` | Receiver dossier |
| `/ledger [id]` | Recent entries or one card |
| `/status [id]` | Active ledger card |
| `/delete <id>` | Delete confirmation |

## Cards

Receive · OCR · Confirmation · Success · History · Error · Edit · Delete

Status rail (one active glow):

```
● RECEIVED
○ OCR VERIFIED
○ WAITING USDT
○ SETTLED
```

## Ledger backends

| Mode | When |
|---|---|
| **Supabase** | `SUPABASE_URL` + `SUPABASE_SECRET_KEY` (or legacy `SUPABASE_SERVICE_ROLE_KEY`) |
| **SQLite** | No secret key / `LEDGER_BACKEND=sqlite` |

When `ALLOWED_USER_IDS` is empty and Supabase is active, the allowlist loads from `admins.telegram_user_id`.

## Architecture

```
bot.py                 entrypoint
ce_vault/
  cards.py             typography-first OLED cards
  console.py           edit-in-place message surface
  handlers.py          commands / media / callbacks
  store.py             backend factory (sqlite | supabase)
  ledger.py            SQLite ledger + rates/balance
  supabase_ledger.py   Supabase PostgREST ledger
  rates.py             quote engine
  ocr.py               vision + text + /demo fixture
  keyboards.py         one-decision actions
  session.py           per-chat console state
  theme.py             status + design tokens
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```
