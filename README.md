# Bot-telegram → CE VAULT

Premium FinTech Operations Console on Telegram.

Not a chatbot. A dark OLED ledger terminal for THB → USDT desk operations:
slip ingest, OCR verification, automatic rate math, settlement, and receiver history.

## เริ่มใช้งานแบบง่ายสุด (3 ขั้น)

1. **Token บอท** — เปิด [@BotFather](https://t.me/BotFather) → `/newbot` หรือคัดลอก token บอทเดิม
2. **Service key (Supabase)** — เปิดลิงก์นี้แล้วกด **Reveal** ที่ `service_role`  
   https://supabase.com/dashboard/project/cewntchvtnuyxvekivwk/settings/api
3. **รัน**

```bash
cp .env.example .env
# วาง token 2 ตัวลง .env แล้ว:
set -a && source .env && set +a
pip install -r requirements.txt
python bot.py
```

ใน `.env` ใส่แค่นี้ก็พอ:

```bash
TELEGRAM_BOT_TOKEN=123456:AA...
SUPABASE_URL=https://cewntchvtnuyxvekivwk.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...   # จากลิงก์ข้อ 2
```

ทดลองทันทีในแชทบอท: ส่ง `/demo`

| ลิงก์ลัด | URL |
|---|---|
| BotFather | https://t.me/BotFather |
| Supabase API keys | https://supabase.com/dashboard/project/cewntchvtnuyxvekivwk/settings/api |
| Supabase Table Editor | https://supabase.com/dashboard/project/cewntchvtnuyxvekivwk/editor |
| PR ล่าสุด (Supabase) | https://github.com/SHELBYY-21/Bot-telegram/pull/15 |
| Telegram Bot API | https://core.telegram.org/bots/api |

> ไม่มี service key ก็รันได้ — จะใช้ SQLite ในเครื่องแทน (`data/vault.db`)

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
| **Supabase** | มี `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` |
| **SQLite** | ไม่มี service key / `LEDGER_BACKEND=sqlite` |

เมื่อ `ALLOWED_USER_IDS` ว่างและใช้ Supabase — ดึง allowlist จาก `admins.telegram_user_id` อัตโนมัติ

## Architecture

```
bot.py                      Telegram console
vault/store.py              Backend factory (sqlite | supabase)
vault/supabase_ledger.py    Supabase ledger
vault/ledger.py             SQLite fallback
vault/cards.py              OLED card UI
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```
