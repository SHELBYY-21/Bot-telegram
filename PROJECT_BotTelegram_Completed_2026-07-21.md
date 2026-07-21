# PROJECT: Bot-telegram (Cursor Cloud Agents Bot)

> **สถานะ:** ✅ Completed / Archived
> **ประเภท:** Telegram Bot + API Integration
> **Repository:** [SHELBYY-21/Bot-telegram](https://github.com/SHELBYY-21/Bot-telegram)
> **ปิดโปรเจค:** 21 กรกฎาคม 2569
> **Merge:** PR [#1](https://github.com/SHELBYY-21/Bot-telegram/pull/1) → `main` (commit `97b9a8d`)

---

## 1. สรุปสุดท้าย — สิ่งที่ส่งมอบ vs เป้าหมายเดิม

**เป้าหมายเดิม:** สร้าง Telegram bot ที่ควบคุม [Cursor Cloud Agents API](https://cursor.com/docs/cloud-agent/api/endpoints) ได้จากแชท — สั่งงาน AI agent, ติดตามสถานะ, และรับผลลัพธ์ (PR) โดยไม่ต้องเปิด Cursor

| เกณฑ์ความสำเร็จ | ผลลัพธ์ | สถานะ |
|---|---|---|
| ครอบคลุม API ทุก endpoint | ครบทั้ง 10 endpoints (`/v0/agents` CRUD + followup/stop/conversation + `/v0/me`, `/v0/models`, `/v0/repositories`) | ✅ |
| สั่งงานจาก Telegram ได้จริง | 13 คำสั่ง: `/agent`, `/agents`, `/status`, `/conversation`, `/followup`, `/stop`, `/delete`, `/models`, `/repos`, `/me`, `/repo`, `/model`, `/start` | ✅ |
| แจ้งเตือนเมื่อ agent ทำงานเสร็จ | Job queue polling ทุก 30 วินาที ส่งสถานะ + ลิงก์ PR เข้าแชทอัตโนมัติ (มี deduplication กัน job ซ้ำ) | ✅ |
| ความปลอดภัย | `ALLOWED_USER_IDS` allowlist, HTML escaping ทุก output, secrets อยู่ใน `.env` (git-ignored) | ✅ |
| ผ่าน code review | Vercel Agent Review ยืนยัน resolved ทั้ง 2 ประเด็น (error handling, job dedup) | ✅ |
| Tests | 10 tests ผ่านหมด (6 API client ผ่าน `httpx.MockTransport` + 4 bot helpers) | ✅ |
| ทดสอบกับ API จริง | **ยังไม่ได้ทำ** — network policy ของ environment บล็อก `api.cursor.com` | ⚠️ ค้าง |

### งานค้างฝั่งผู้ใช้ (ก่อนใช้งานจริง)

- 🔴 **Rotate Cursor API keys ทั้ง 2 ตัว** (`crsr_fbc7...` และ `crsr_0646...`) — เคยส่งผ่านแชทแล้ว ถือว่า semi-exposed
- 🟠 ทดสอบกับ API จริงบนเครื่องตัวเอง: `curl -H "Authorization: Bearer $CURSOR_API_KEY" https://api.cursor.com/v0/me` แล้วรัน `python bot.py` — field names ใน response อาจต้องปรับเล็กน้อย เพราะ spec มาจากแหล่งรอง (เอกสารทางการถูกบล็อกจาก environment นี้)
- 🟡 ถ้าจะรัน 24/7: ต้องหาที่ deploy (VPS / Railway / Docker) — ยังไม่ได้ทำในเฟสนี้

---

## 2. Reusable Assets — ชิ้นส่วนที่นำไปใช้ต่อได้

| Asset | ไฟล์ | ใช้ซ้ำกับ |
|---|---|---|
| **Async API client pattern** — httpx client + Bearer auth + error class เดียว + `transport` injection สำหรับ test | `cursor_api.py` | wrapper ของ REST API ตัวไหนก็ได้ เปลี่ยนแค่ endpoints |
| **Telegram bot skeleton** — command handlers + allowlist auth + per-chat settings (`state.json`) + HTML-safe reply helper | `bot.py` | บอทตัวถัดไปทุกตัว (copy โครงแล้วเปลี่ยน handlers) |
| **Status-polling job pattern** — `run_repeating` + terminal-status set + dedup ด้วย `get_jobs_by_name` | `bot.py` (`watch_agent`, `poll_agent`) | งาน "เฝ้าสถานะแล้วแจ้งเตือน" ทุกแบบ |
| **MockTransport test pattern** — test API client โดยไม่ยิง network จริง | `tests/test_cursor_api.py` | ทุกโปรเจคที่ใช้ httpx |
| **`.env.example` + `.gitignore` combo** | root | ทุกโปรเจคที่มี secrets |

---

## 3. Reusable Workflows — สิ่งที่ควรจดเป็น template

1. **API docs ถูกบล็อก → หาแหล่งรอง:** ใช้ web search + README ของ open-source wrapper (MCP server ของ community) เพื่อ reconstruct endpoint spec แล้วระบุความเสี่ยงไว้ชัด ๆ ว่า spec มาจากแหล่งรอง
2. **Review-bot loop:** push → รอ review comments → แก้เฉพาะที่ valid → push → bot ยืนยัน resolved เอง ไม่ต้องตอบ comment ทีละอัน
3. **Remote environment network policy:** ถ้าต้องให้ Claude ทดสอบ external API ได้ ให้เพิ่ม domain (เช่น `api.cursor.com`) ใน allowed domains ของ environment ที่ claude.ai/code **ก่อน** เริ่ม session

---

## 4. Changelog

| วันที่ | Commit | รายการ |
|---|---|---|
| 20 ก.ค. 2569 | `5c17ada` | สร้างบอท + API client ครบทุก endpoint |
| 20 ก.ค. 2569 | `ccdc982` | แก้ตาม review: error handling ใน list commands + job dedup |
| 20 ก.ค. 2569 | `31f8387` | เพิ่ม `/conversation` + โครง tests |
| 20 ก.ค. 2569 | `b01329f` | test suite เต็ม (10 tests) + `requirements-dev.txt` |
| 20 ก.ค. 2569 | `97b9a8d` | **Squash-merge PR #1 → `main`** — โปรเจคเสร็จสมบูรณ์ |
| 21 ก.ค. 2569 | — | ปิดโปรเจค + จัดเก็บเอกสารนี้ |

---

*เอกสารนี้จัดเก็บตาม convention: `PROJECT_BotTelegram_Completed_2026-07-21.md`*
