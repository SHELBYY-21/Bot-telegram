"""Optional bridge: Cursor Cloud Agents commands (backward compatible).

Enabled only when ENABLE_CURSOR_AGENTS=1 and CURSOR_API_KEY is set.
Keeps agent management available without polluting the CE VAULT UX.
"""

from __future__ import annotations

import html
import json
import logging
import os

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from cursor_api import CursorAPIError, CursorClient

logger = logging.getLogger("agents_bridge")

TERMINAL_STATUSES = {
    "FINISHED",
    "COMPLETED",
    "ERROR",
    "FAILED",
    "EXPIRED",
    "STOPPED",
    "CANCELLED",
}
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "30"))


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


def _authorized(update: Update) -> bool:
    from ce_vault.handlers.console import authorized

    return authorized(update)


async def poll_agent(context: ContextTypes.DEFAULT_TYPE) -> None:
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


async def cmd_repo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    import bot as bot_mod

    if not context.args:
        await reply(update, "Usage: /repo &lt;github-url&gt; [ref]")
        return
    state = context.application.bot_data["state"]
    settings = bot_mod.chat_settings(state, update.effective_chat.id)
    settings["repository"] = context.args[0]
    settings["ref"] = context.args[1] if len(context.args) > 1 else None
    bot_mod.save_state(state)
    ref = settings["ref"] or "default branch"
    await reply(
        update,
        f"Repository set to {html.escape(settings['repository'])} ({html.escape(ref)})",
    )


async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    import bot as bot_mod

    if not context.args:
        await reply(update, "Usage: /model &lt;model-name&gt;")
        return
    state = context.application.bot_data["state"]
    settings = bot_mod.chat_settings(state, update.effective_chat.id)
    settings["model"] = context.args[0]
    bot_mod.save_state(state)
    await reply(update, f"Model set to <code>{html.escape(settings['model'])}</code>")


async def cmd_models(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
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
    if not _authorized(update):
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
    if not _authorized(update):
        return
    import bot as bot_mod

    prompt = " ".join(context.args or [])
    if not prompt:
        await reply(update, "Usage: /agent &lt;prompt&gt;")
        return
    state = context.application.bot_data["state"]
    settings = bot_mod.chat_settings(state, update.effective_chat.id)
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
            auto_create_pr=os.environ.get("AUTO_CREATE_PR", "").lower()
            in ("1", "true", "yes"),
        )
    except CursorAPIError as e:
        await reply(update, f"Failed to launch agent: {html.escape(str(e))}")
        return
    watch_agent(context, update.effective_chat.id, agent)
    await reply(update, "Agent launched\n" + fmt_agent(agent))


async def cmd_agents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
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
    await reply(update, "\n\n".join(fmt_agent(a) for a in agents))


async def _require_id(update: Update, context: ContextTypes.DEFAULT_TYPE, usage: str) -> str | None:
    if not context.args:
        await reply(update, usage)
        return None
    return context.args[0]


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
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
    if not _authorized(update):
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
    if len(out) > 3900:
        out = "…" + out[-3900:]
    await reply(update, out)


async def cmd_followup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
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
    if not _authorized(update):
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


async def cmd_adelete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Agent delete — uses /adelete to avoid clashing with CE VAULT /delete."""
    if not _authorized(update):
        return
    agent_id = await _require_id(update, context, "Usage: /adelete &lt;agent-id&gt;")
    if not agent_id:
        return
    try:
        await cursor(context).delete_agent(agent_id)
    except CursorAPIError as e:
        await reply(update, html.escape(str(e)))
        return
    await reply(update, f"Deleted <code>{html.escape(agent_id)}</code>")


async def cmd_me(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    try:
        info = await cursor(context).me()
    except CursorAPIError as e:
        await reply(update, html.escape(str(e)))
        return
    await reply(update, f"<pre>{html.escape(json.dumps(info, indent=2))}</pre>")


def register(application: Application) -> None:
    handlers = {
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
        "adelete": cmd_adelete,
        "me": cmd_me,
    }
    for name, fn in handlers.items():
        application.add_handler(CommandHandler(name, fn))
