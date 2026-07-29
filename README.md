# Bot-telegram → CE VAULT

Premium FinTech Operations Console on Telegram (OLED ledger — not a chatbot).

## รันแบบขี้เกียจสุด

**จำเป็นแค่ token บอท** — Supabase ไม่บังคับ (ไม่มีก็ใช้ SQLite ให้เอง)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

เปิด `.env` ใส่แค่บรรทัดนี้ (เอาจาก https://t.me/BotFather):

```bash
TELEGRAM_BOT_TOKEN=123456:AA...
```

แล้วรัน:

```bash
python bot.py
```

ในแชทบอทพิมพ์ `/demo`

หรือสั้นกว่านั้น:

```bash
./start.sh
```

### (ไม่บังคับ) ต่อ Supabase

เปิด https://supabase.com/dashboard/project/cewntchvtnuyxvekivwk/settings/api  
แล้วเติมใน `.env`:

```bash
SUPABASE_URL=https://cewntchvtnuyxvekivwk.supabase.co
SUPABASE_SECRET_KEY=sb_secret_...
# หรือ JWT เก่า:
# SUPABASE_SERVICE_ROLE_KEY=eyJ...
```

| ลิงก์ลัด | |
|---|---|
| BotFather | https://t.me/BotFather |
| Supabase API keys | https://supabase.com/dashboard/project/cewntchvtnuyxvekivwk/settings/api |
| Table Editor | https://supabase.com/dashboard/project/cewntchvtnuyxvekivwk/editor |
| PR | https://github.com/SHELBYY-21/Bot-telegram/pull/15 |

## คำสั่งในบอท

| Command | ทำอะไร |
|---|---|
| `/start` | หน้าแรก |
| `/demo` | ทดลองสลิปปลอม |
| `/rates` | อัตรา + ยอด USDT |
| `/setrates <buy> <sell>` | ตั้งอัตรา |
| `/balance [usdt]` | ดู/ตั้งยอด |
| `/history [BANK last4]` | ประวัติผู้รับ |
| `/ledger [id]` | ดูรายการ |
| `/delete <id>` | ลบ |

## ทดสอบ

```bash
pip install -r requirements-dev.txt
pytest -q
```

## โครงสร้าง

```
bot.py                   โหลด .env เอง → รันคอนโซล
start.sh                 one-liner สำหรับขี้เกียจ
vault/store.py           sqlite | supabase อัตโนมัติ
vault/cards.py           การ์ด OLED
```
