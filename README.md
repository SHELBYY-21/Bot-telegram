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

## OCR

Slips are read by an OpenAI-compatible vision model. Provider is picked from
the environment:

| Env | Endpoint | Default model |
|---|---|---|
| `GROK_API_KEY` | `api.x.ai` | `grok-2-vision-1212` |
| `OPENAI_API_KEY` | `api.openai.com` | `gpt-4o-mini` |
| `OCR_API_KEY` | `OCR_API_BASE` | `OCR_MODEL` |

**Grok wins when both it and an OpenAI key are set** — it reads Thai slips
noticeably better. `OCR_API_KEY` outranks both, and `OCR_API_BASE` /
`OCR_MODEL` override the chosen defaults so any compatible host works.

`GROK_MODEL` must name a **vision** model. A text-only Grok model returns
nothing useful for an image and the bot falls back to the text parser.

With no key set, OCR uses the built-in text parser only (`/demo` still works).

## Slip storage

The slip image is the evidence behind a ledger row, so it is stored durably:

| Mode | When |
|---|---|
| **Supabase Storage** | `SUPABASE_URL` + server key — survives the container and the bot token |
| **Local disk** | otherwise, under `IMAGES_DIR` (needs a volume to persist) |
| **Off** | `SLIP_STORAGE=none` |

Force local with `SLIP_STORAGE=local`. Objects are keyed
`YYYY/MM/<sha256>.jpg`, so re-uploading the same slip overwrites rather than
duplicating. Uploads are best-effort — a storage outage logs a warning and
still lets the desk book the trade.

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
  storage.py           slip image storage (supabase | local | none)
  keyboards.py         one-decision actions
  session.py           per-chat console state
  theme.py             status + design tokens
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Deploy (Fly.io)

CE VAULT is a **worker**, not a web app — it long-polls Telegram and never
receives inbound HTTP. `fly.toml` therefore declares no `[http_service]`, so
the machine runs continuously instead of being auto-stopped for idleness.

```bash
fly volumes create ce_vault_data --region sin --size 1   # once
fly secrets set \
  TELEGRAM_BOT_TOKEN='…' \
  SUPABASE_URL='https://<project>.supabase.co' \
  SUPABASE_SECRET_KEY='…' \
  ALLOWED_USER_IDS='11111111 22222222' \
  OCR_API_KEY='…'
fly deploy
fly logs
```

Non-secret settings (`TIMEZONE`, `LEDGER_BACKEND`, paths) live in `fly.toml`
under `[env]`. Everything above goes through `fly secrets` so it is never
committed and never appears in build logs.

**Run exactly one machine.** Two instances would both long-poll and process
every Telegram update twice — double ledger rows. The `[mounts]` volume pins
the app to a single machine; verify with `fly scale count 1`.

Persistent state on the volume at `/data`: `state.json` (in-flight per-chat
sessions), `vault.db` (SQLite ledger when Supabase is unset), and `slips/`
(only when slip storage falls back to local — with Supabase configured the
images go to the bucket instead and the volume just holds session state).
