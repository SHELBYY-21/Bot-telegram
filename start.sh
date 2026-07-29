#!/usr/bin/env bash
# CE VAULT — one command start
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env — paste TELEGRAM_BOT_TOKEN from https://t.me/BotFather then re-run ./start.sh"
  exit 1
fi

if ! grep -qE '^TELEGRAM_BOT_TOKEN=.+' .env; then
  echo "Open .env and set TELEGRAM_BOT_TOKEN=... from https://t.me/BotFather"
  exit 1
fi

exec python bot.py
