"""Telegram bot for launching and managing Cursor Cloud Agents.

Commands:
  /start /help          — usage
  /repo <url> [ref]     — set the default repository for this chat
  /model <name>         — set the default model for this chat
  /models               — list available models
  /repos                — list repositories the API key can access
  /agent <prompt>       — launch a cloud agent on the configured repo
  /agents               — list recent agents
  /status <id>          — show one agent's status
  /conversation <id>    — show an agent's conversation history
  /followup <id> <text> — send follow-up instructions to an agent
  /stop <id>            — stop a running agent
  /delete <id>          — delete an agent
  /me                   — show Cursor API key info
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import os
from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from cursor_api import CursorAPIError, CursorClient

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO
)
logger = logging.getLogger("bot")

STATE_FILE = Path(os.environ.get("STATE_FILE", "state.json"))

# Statuses that mean the agent is done and polling can stop.
TERMINAL_STATUSES = {"FINISHED", "COMPLETED", "ERROR", "FAILED", "EXPIRED", "STOPPED", "CANCELLED"}
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "30"))


# --- per-chat settings persistence ---------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            logger.warning("state file corrupt, starting fresh")
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def chat_settings(state: dict, chat_id: int) -> dict:
    return state.setdefault(str(chat_id), {})


# --- auth ----------------------------------------------------------------

def allowed_user_ids() -> set[int]:
    raw = os.environ.get("ALLOWED_USER_IDS", "").strip()
    return {int(x) for x in raw.replace(",", " ").split()} if raw else set()


def authorized(update: Update) -> bool:
    allowed = allowed_user_ids()
    if not allowed:
        return True  # no allowlist configured — open bot
    return bool(update.effective_user) and update.effective_user.id in allowed


# --- formatting ----------------------------------------------------------

def fmt_agent(agent: dict) -> str:
    lines = [
        f"<b>{html.escape(agent.get('name') or agent.get('id', '?'))}</b>",
        f"id: <code>{html.escape(str(agent.get('id', '?')))}</code>",
        f"status: <b>{html.escape(str(agent.get('status', 'UNKNOWN')))}</b>",
    ]
    source = agent.get("source") or {}
    if source.get("repository"):
        lines.append(f"repo: {html.escape(source['repository'])}")
    target = agent.get("target") or {}
    if target.get("branchName"):
        lines.append(f"branch: <code>{html.escape(target['branchName'])}</code>")
    if target.get("prUrl"):
        lines.append(f"PR: {html.escape(target['prUrl'])}")
    if agent.get("summary"):
        lines.append(f"summary: {html.escape(agent['summary'])}")
    return "\n".join(lines)


async def reply(update: Update, text: str) -> None:
    assert update.effective_message
    await update.effective_message.reply_text(
        text, parse_mode=ParseMode.HTML, disable_web_page_preview=True
    )


def cursor(context: ContextTypes.DEFAULT_TYPE) -> CursorClient:
    return context.application.bot_data["cursor"]


# --- background status polling -------------------------------------------

async def poll_agent(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Repeating job: watch one agent until it reaches a terminal status."""
    job = context.job
    assert job and job.data
    agent_id: str = job.data["agent_id"]
    chat_id: int = job.data["chat_id"]
    try:
        agent = await cursor(context).get_agent(agent_id)
    except CursorAPIError as e:
        logger.warning("poll failed for %s: %s", agent_id, e)
        if e.status_code == 404:
            job.schedule_removal()
        return
    status = str(agent.get("status", "")).upper()
    last = job.data.get("last_status")
    if status != last:
        job.data["last_status"] = status
        await context.bot.send_message(
            chat_id,
            fmt_agent(agent),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    if status in TERMINAL_STATUSES:
        job.schedule_removal()


def watch_agent(context: ContextTypes.DEFAULT_TYPE, chat_id: int, agent: dict) -> None:
    if not context.job_queue:
        return
    name = f"poll:{agent['id']}"
    if context.job_queue.get_jobs_by_name(name):
        return
    context.job_queue.run_repeating(
        poll_agent,
        interval=POLL_INTERVAL,
        first=POLL_INTERVAL,
        name=name,
        data={
            "agent_id": agent["id"],
            "chat_id": chat_id,
            "last_status": str(agent.get("status", "")).upper(),
        },
    )


# --- command handlers ----------------------------------------------------

HELP = (
    "Cursor Cloud Agents bot.\n\n"
    "/repo &lt;url&gt; [ref] — set default repository\n"
    "/model &lt;name&gt; — set default model\n"
    "/models — list available models\n"
    "/repos — list accessible repositories\n"
    "/agent &lt;prompt&gt; — launch a cloud agent\n"
    "/agents — list recent agents\n"
    "/status &lt;id&gt; — agent status\n"
    "/conversation &lt;id&gt; — agent conversation history\n"
    "/followup &lt;id&gt; &lt;text&gt; — send follow-up\n"
    "/stop &lt;id&gt; — stop agent\n"
    "/delete &lt;id&gt; — delete agent\n"
    "/me — API key info"
)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    await reply(update, HELP)


async def cmd_repo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not context.args:
        await reply(update, "Usage: /repo &lt;github-url&gt; [ref]")
        return
    state = context.application.bot_data["state"]
    settings = chat_settings(state, update.effective_chat.id)
    settings["repository"] = context.args[0]
    settings["ref"] = context.args[1] if len(context.args) > 1 else None
    save_state(state)
    ref = settings["ref"] or "default branch"
    await reply(update, f"Repository set to {html.escape(settings['repository'])} ({html.escape(ref)})")


async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not context.args:
        await reply(update, "Usage: /model &lt;model-name&gt;")
        return
    state = context.application.bot_data["state"]
    settings = chat_settings(state, update.effective_chat.id)
    settings["model"] = context.args[0]
    save_state(state)
    await reply(update, f"Model set to <code>{html.escape(settings['model'])}</code>")


async def cmd_models(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    try:
        data = await cursor(context).list_models()
    except CursorAPIError as e:
        await reply(update, html.escape(str(e)))
        return
    models = data.get("models", data if isinstance(data, list) else [])
    if not models:
        await reply(update, "No models returned.")
        return
    await reply(update, "\n".join(f"• <code>{html.escape(str(m))}</code>" for m in models))


async def cmd_repos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    try:
        data = await cursor(context).list_repositories()
    except CursorAPIError as e:
        await reply(update, html.escape(str(e)))
        return
    repos = data.get("repositories", [])
    if not repos:
        await reply(update, "No repositories returned.")
        return
    lines = []
    for r in repos[:50]:
        if isinstance(r, dict):
            lines.append(f"• {html.escape(r.get('repository') or r.get('url') or str(r))}")
        else:
            lines.append(f"• {html.escape(str(r))}")
    await reply(update, "\n".join(lines))


async def cmd_agent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    prompt = " ".join(context.args or [])
    if not prompt:
        await reply(update, "Usage: /agent &lt;prompt&gt;")
        return
    state = context.application.bot_data["state"]
    settings = chat_settings(state, update.effective_chat.id)
    repository = settings.get("repository") or os.environ.get("DEFAULT_REPOSITORY")
    if not repository:
        await reply(update, "No repository configured. Set one with /repo &lt;url&gt; first.")
        return
    try:
        agent = await cursor(context).create_agent(
            prompt_text=prompt,
            repository=repository,
            ref=settings.get("ref"),
            model=settings.get("model") or os.environ.get("DEFAULT_MODEL"),
            auto_create_pr=os.environ.get("AUTO_CREATE_PR", "").lower() in ("1", "true", "yes"),
        )
    except CursorAPIError as e:
        await reply(update, f"Failed to launch agent: {html.escape(str(e))}")
        return
    watch_agent(context, update.effective_chat.id, agent)
    await reply(update, "Agent launched 🚀\n" + fmt_agent(agent))


async def cmd_agents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    try:
        data = await cursor(context).list_agents(limit=10)
    except CursorAPIError as e:
        await reply(update, html.escape(str(e)))
        return
    agents = data.get("agents", [])
    if not agents:
        await reply(update, "No agents found.")
        return
    blocks = [fmt_agent(a) for a in agents]
    await reply(update, "\n\n".join(blocks))


async def _require_id(update: Update, context: ContextTypes.DEFAULT_TYPE, usage: str) -> str | None:
    if not context.args:
        await reply(update, usage)
        return None
    return context.args[0]


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    agent_id = await _require_id(update, context, "Usage: /status &lt;agent-id&gt;")
    if not agent_id:
        return
    try:
        agent = await cursor(context).get_agent(agent_id)
    except CursorAPIError as e:
        await reply(update, html.escape(str(e)))
        return
    await reply(update, fmt_agent(agent))


async def cmd_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    agent_id = await _require_id(update, context, "Usage: /conversation &lt;agent-id&gt;")
    if not agent_id:
        return
    try:
        data = await cursor(context).get_conversation(agent_id)
    except CursorAPIError as e:
        await reply(update, html.escape(str(e)))
        return
    messages = data.get("messages", [])
    if not messages:
        await reply(update, "No messages in this conversation.")
        return
    lines = []
    for m in messages:
        role = m.get("type") or m.get("role") or "message"
        text = m.get("text") or ""
        lines.append(f"<b>{html.escape(str(role))}</b>: {html.escape(text)}")
    out = "\n\n".join(lines)
    # Telegram messages cap at 4096 chars; keep the most recent part.
    if len(out) > 3900:
        out = "…" + out[-3900:]
    await reply(update, out)


async def cmd_followup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    if not context.args or len(context.args) < 2:
        await reply(update, "Usage: /followup &lt;agent-id&gt; &lt;instructions&gt;")
        return
    agent_id, text = context.args[0], " ".join(context.args[1:])
    try:
        await cursor(context).add_followup(agent_id, text)
    except CursorAPIError as e:
        await reply(update, html.escape(str(e)))
        return
    watch_agent(context, update.effective_chat.id, {"id": agent_id, "status": "RUNNING"})
    await reply(update, f"Follow-up sent to <code>{html.escape(agent_id)}</code>")


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    agent_id = await _require_id(update, context, "Usage: /stop &lt;agent-id&gt;")
    if not agent_id:
        return
    try:
        await cursor(context).stop_agent(agent_id)
    except CursorAPIError as e:
        await reply(update, html.escape(str(e)))
        return
    await reply(update, f"Stopped <code>{html.escape(agent_id)}</code>")


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    agent_id = await _require_id(update, context, "Usage: /delete &lt;agent-id&gt;")
    if not agent_id:
        return
    try:
        await cursor(context).delete_agent(agent_id)
    except CursorAPIError as e:
        await reply(update, html.escape(str(e)))
        return
    await reply(update, f"Deleted <code>{html.escape(agent_id)}</code>")


async def cmd_me(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    try:
        info = await cursor(context).me()
    except CursorAPIError as e:
        await reply(update, html.escape(str(e)))
        return
    await reply(update, f"<pre>{html.escape(json.dumps(info, indent=2))}</pre>")


# --- app lifecycle -------------------------------------------------------

async def on_shutdown(application: Application) -> None:
    client: CursorClient = application.bot_data["cursor"]
    await client.close()


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    api_key = os.environ.get("CURSOR_API_KEY")
    if not token or not api_key:
        raise SystemExit("TELEGRAM_BOT_TOKEN and CURSOR_API_KEY must be set")

    application = Application.builder().token(token).post_shutdown(on_shutdown).build()
    application.bot_data["cursor"] = CursorClient(api_key)
    application.bot_data["state"] = load_state()

    handlers = {
        "start": cmd_start,
        "help": cmd_start,
        "repo": cmd_repo,
        "model": cmd_model,
        "models": cmd_models,
        "repos": cmd_repos,
        "agent": cmd_agent,
        "agents": cmd_agents,
        "status": cmd_status,
        "conversation": cmd_conversation,
        "followup": cmd_followup,
        "stop": cmd_stop,
        "delete": cmd_delete,
        "me": cmd_me,
    }
    for name, fn in handlers.items():
        application.add_handler(CommandHandler(name, fn))

    logger.info("bot starting (polling)")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
