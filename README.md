# Bot-telegram → CE VAULT

Premium FinTech Operations Console on Telegram.

Not a chatbot. A dark OLED ledger terminal for THB → USDT desk operations:
slip ingest, OCR verification, automatic rate math, settlement, and receiver history.

## เริ่มใช้งานแบบง่ายสุด (3 ขั้น)

1. **Token บอท** — https://t.me/BotFather  
2. **Keys** — https://supabase.com/dashboard/project/cewntchvtnuyxvekivwk/settings/api  
   คัดลอก `Publishable key` + `Secret key` (รูปแบบใหม่ `sb_publishable_…` / `sb_secret_…`)  
3. **รัน**

```bash
cp .env.example .env
# วางค่าลง .env แล้ว:
set -a && source .env && set +a
pip install -r requirements.txt
python bot.py
```

ใน `.env` ใส่แค่นี้:

```bash
TELEGRAM_BOT_TOKEN=123456:AA...
SUPABASE_URL=https://cewntchvtnuyxvekivwk.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
SUPABASE_SECRET_KEY=sb_secret_...
SUPABASE_JWKS_URL=https://cewntchvtnuyxvekivwk.supabase.co/auth/v1/.well-known/jwks.json
```

ทดลองทันทีในแชทบอท: ส่ง `/demo`

| ลิงก์ลัด | URL |
|---|---|
| BotFather | https://t.me/BotFather |
| Supabase API keys | https://supabase.com/dashboard/project/cewntchvtnuyxvekivwk/settings/api |
| Supabase Table Editor | https://supabase.com/dashboard/project/cewntchvtnuyxvekivwk/editor |
| PR (Supabase) | https://github.com/SHELBYY-21/Bot-telegram/pull/15 |

> โปรเจกต์นี้เป็น **Python** — ใช้ `SUPABASE_SECRET_KEY` กับ PostgREST โดยตรง ไม่ต้อง `npm install @supabase/server`  
> ไม่มี secret key ก็รันได้ (fallback เป็น SQLite ที่ `data/vault.db`)

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

## Setup (รายละเอียด)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
set -a && source .env && set +a
python bot.py
```

### Ledger backends

| Mode | When |
|---|---|
| **Supabase** | มี `SUPABASE_URL` + `SUPABASE_SECRET_KEY` (หรือ legacy `SUPABASE_SERVICE_ROLE_KEY`) |
| **SQLite** | ไม่มี secret key / `LEDGER_BACKEND=sqlite` |

เมื่อ `ALLOWED_USER_IDS` ว่างและใช้ Supabase — ดึง allowlist จาก `admins.telegram_user_id` อัตโนมัติ

## Architecture

```
bot.py                      Telegram console
vault/store.py              Backend factory (sqlite | supabase)
vault/supabase_ledger.py    Supabase ledger
vault/ledger.py             SQLite fallback
vault/cards.py              OLED card UI
cursor_bot.py               Legacy Cursor Cloud Agents bot
```

## Legacy Mode

The original Cursor Cloud Agents bot is preserved for backward compatibility:

```bash
LEGACY_CURSOR_BOT=1 python bot.py
```

Requires `CURSOR_API_KEY` in addition to `TELEGRAM_BOT_TOKEN`. See `cursor_bot.py` and `cursor_api.py`.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```
