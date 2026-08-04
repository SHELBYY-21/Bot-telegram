# CE VAULT — Telegram long-polling worker.
#
# This is NOT a web app: there is no WSGI/ASGI entrypoint and no port to
# serve. The container runs one process that holds an outbound long-poll
# connection to api.telegram.org for its entire lifetime.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first so code edits don't invalidate the wheel layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py ./
COPY ce_vault/ ./ce_vault/

# Writable state lives on the Fly volume mounted at /data (see fly.toml).
# Defaults here so the image also runs standalone via `docker run -v`.
ENV STATE_FILE=/data/state.json \
    LEDGER_DB=/data/vault.db \
    IMAGES_DIR=/data/slips \
    TIMEZONE=Asia/Bangkok

# Runs as root: a Fly volume mounts root-owned, and this is a single-tenant
# micro-VM running exactly one process. Dropping privileges here would mean
# chown-ing the mount on every boot for no meaningful isolation gain.
CMD ["python", "bot.py"]
