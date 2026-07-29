# Bot-telegram → CE VAULT

Premium FinTech Operations Console on Telegram.

Not a chatbot. A dark OLED ledger terminal for THB → USDT desk operations:
slip ingest, OCR verification, automatic rate math, settlement, and receiver history.

## Operator flow

1. Send a **bank slip image** (or paste slip text), **or** type a **USDT amount**
2. Console runs Vision / parse → shows **OCR card** → **Confirmation card**
3. **Confirm** → Waiting USDT → **Mark Settled** → **Success card**
4. Edit / Cancel / Delete as needed — one card per screen, messages edit in place

Buy rate is never requested during a transaction. The rate desk publishes once via `/setrates`.

## Commands

| Command | Purpose |
|---|---|
| `/start` | Console home |
| `/demo` | Offline fixture slip (no image needed) |
| `/rates` | Rate desk + USDT balance |
| `/setrates <buy> <sell>` | Publish desk rates |
| `/balance [usdt]` | Show or set USDT float |
| `/history [BANK last4]` | Receiver dossier |
| `/ledger [id]` | Recent entries or one ledger card |
| `/delete <id>` | Delete confirmation |

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Required: TELEGRAM_BOT_TOKEN
# Recommended: SUPABASE_SERVICE_ROLE_KEY (Dashboard → Project Settings → API)
set -a && source .env && set +a
python bot.py
```

### Ledger backends

| Mode | When |
|---|---|
| **Supabase** | `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` (or `LEDGER_BACKEND=supabase`) |
| **SQLite** | fallback / `LEDGER_BACKEND=sqlite` → `data/vault.db` |

Linked project: Supabase **Bot-telegram** (`cewntchvtnuyxvekivwk`) — `transactions`, `admins`, `rates`, `receivers`, …

When `ALLOWED_USER_IDS` is empty and Supabase is active, allowlist comes from `admins.telegram_user_id`.

Optional: set `OCR_API_KEY` for Vision OCR. Without it, captions / pasted slip text are parsed.

## Architecture

```
bot.py                      Telegram console (edit-in-place UX)
vault/
  cards.py                  One-card renderers
  store.py                  Backend factory (sqlite | supabase)
  ledger.py                 SQLite WAL ledger
  supabase_ledger.py        Supabase PostgREST ledger
  rates.py / ocr.py / theme.py / keyboards.py
cursor_api.py               Legacy Cursor Cloud Agents client
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Design language

- Dark OLED hierarchy, typography-first
- Monospace for every number
- Status rail: `● RECEIVED` → `● OCR VERIFIED` → `● WAITING USDT` → `● SETTLED` (one glow)
- Never spam — edit the previous console message whenever possible
