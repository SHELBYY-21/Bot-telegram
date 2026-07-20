# Bot-telegram

Telegram bot for launching and managing [Cursor Cloud Agents](https://cursor.com/docs/cloud-agent/api/endpoints) from chat.

## What it does

Wraps the Cursor Cloud Agents API (`https://api.cursor.com`):

| Command | API endpoint |
|---|---|
| `/agent <prompt>` | `POST /v0/agents` — launch an agent on the configured repo |
| `/agents` | `GET /v0/agents` — list recent agents |
| `/status <id>` | `GET /v0/agents/{id}` |
| `/conversation <id>` | `GET /v0/agents/{id}/conversation` |
| `/followup <id> <text>` | `POST /v0/agents/{id}/followup` |
| `/stop <id>` | `POST /v0/agents/{id}/stop` |
| `/delete <id>` | `DELETE /v0/agents/{id}` |
| `/models` | `GET /v0/models` |
| `/repos` | `GET /v0/repositories` |
| `/me` | `GET /v0/me` |
| `/repo <url> [ref]` | set the default repository for the chat |
| `/model <name>` | set the default model for the chat |

After launching an agent (or sending a follow-up) the bot polls its status every 30 seconds and pushes updates to the chat — including the PR URL when the agent finishes.

## Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Create a Cursor API key (Cursor Dashboard → Integrations → API Keys).
3. Configure and run:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # fill in tokens
set -a && source .env && set +a
python bot.py
```

Set `ALLOWED_USER_IDS` in `.env` to restrict the bot to specific Telegram users — leave it empty and anyone who finds the bot can spend your Cursor credits.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Files

- `bot.py` — Telegram bot (python-telegram-bot, long polling) and status-watch job queue
- `cursor_api.py` — async client for the Cloud Agents API
- `state.json` — per-chat repo/model settings (created at runtime, git-ignored)
