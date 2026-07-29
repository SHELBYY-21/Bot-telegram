"""CE VAULT — Premium FinTech Operations Console (Telegram).

Primary surface: slip OCR + USDT intake + ledger settlement.
Backward compatible: Cursor Cloud Agents commands remain available
under the same console card language.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ce_vault import cards, handlers as vault, keyboards
from ce_vault.design import AGENT_PIPELINE
from ce_vault.ledger import Ledger
from ce_vault.messaging import send_card, show_typing, track_console_message
from cursor_api import CursorAPIError, CursorClient

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO
)
logger = logging.getLogger("bot")

STATE_FILE = Path(os.environ.get("STATE_FILE", "state.json"))
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
        return True
    return bool(update.effective_user) and update.effective_user.id in allowed


def require_auth(handler):
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not authorized(update):
            return
        return await handler(update, context)

    return wrapped


# --- formatting (backward-compatible export for tests) -------------------

def fmt_agent(agent: dict) -> str:
    """Premium agent card — replaces the legacy plain-text formatter."""
    return cards.agent_card(agent)


async def reply(update: Update, text: str) -> None:
    await send_card(update, text)


def cursor(context: ContextTypes.DEFAULT_TYPE) -> CursorClient:
    return context.application.bot_data["cursor"]


# --- background status polling -------------------------------------------

async def poll_agent(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    assert job and job.data
    agent_id: str = job.data["agent_id"]
    chat_id: int = job.data["chat_id"]
    message_id: int | None = job.data.get("message_id")
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
        if status in {"FINISHED", "COMPLETED"}:
            text = cards.agent_success_card(agent)
        elif status in {"ERROR", "FAILED", "EXPIRED"}:
            text = cards.error_card(
                problem="Agent failed",
                cause=f"Status {status}",
                action="Inspect /conversation or relaunch",
            )
        else:
            text = cards.agent_card(agent)
        try:
            if message_id:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                    reply_markup=keyboards.agent_actions(agent_id)
                    if status not in TERMINAL_STATUSES
                    else None,
                )
            else:
                msg = await context.bot.send_message(
                    chat_id,
                    text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                job.data["message_id"] = msg.message_id
        except Exception as e:
            logger.debug("status push failed: %s", e)
    if status in TERMINAL_STATUSES:
        job.schedule_removal()


def watch_agent(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    agent: dict,
    message_id: int | None = None,
) -> None:
    if not context.job_queue:
        return
    name = f"poll:{agent['id']}"
    existing = context.job_queue.get_jobs_by_name(name)
    if existing:
        if message_id:
            for job in existing:
                if job.data is not None:
                    job.data["message_id"] = message_id
        return
    context.job_queue.run_repeating(
        poll_agent,
        interval=POLL_INTERVAL,
        first=POLL_INTERVAL,
        name=name,
        data={
            "agent_id": agent["id"],
            "chat_id": chat_id,
            "message_id": message_id,
            "last_status": str(agent.get("status", "")).upper(),
        },
    )


# --- CE VAULT commands ---------------------------------------------------

@require_auth
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await vault.cmd_console_home(update, context)


@require_auth
async def cmd_rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await vault.cmd_rates(update, context)


@require_auth
async def cmd_usdt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await vault.cmd_usdt(update, context)


@require_auth
async def cmd_ledger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await vault.cmd_ledger(update, context)


@require_auth
async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await vault.cmd_history(update, context)


@require_auth
async def cmd_recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await vault.cmd_recent(update, context)


@require_auth
async def cmd_void(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await vault.cmd_delete_ledger(update, context)


@require_auth
async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await vault.handle_photo(update, context)


@require_auth
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await vault.handle_text_slip(update, context)


@require_auth
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await vault.on_callback(update, context)


# --- Cursor agent commands (restyled) ------------------------------------

@require_auth
async def cmd_repo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await send_card(
            update,
            cards.error_card(
                problem="Missing repository",
                cause="URL required",
                action="Send /repo <github-url> [ref]",
            ),
        )
        return
    state = context.application.bot_data["state"]
    settings = chat_settings(state, update.effective_chat.id)
    settings["repository"] = context.args[0]
    settings["ref"] = context.args[1] if len(context.args) > 1 else None
    save_state(state)
    ref = settings["ref"] or "default"
    text = "\n".join(
        [
            cards.header(subtitle="Workspace"),
            "",
            cards.row("Repository", cards.esc(settings["repository"])),
            "",
            cards.row("Ref", cards.mono(ref)),
            "",
            cards.divider(),
        ]
    )
    await send_card(update, text)


@require_auth
async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await send_card(
            update,
            cards.error_card(
                problem="Missing model",
                cause="Name required",
                action="Send /model <name>",
            ),
        )
        return
    state = context.application.bot_data["state"]
    settings = chat_settings(state, update.effective_chat.id)
    settings["model"] = context.args[0]
    save_state(state)
    text = "\n".join(
        [
            cards.header(subtitle="Workspace"),
            "",
            cards.row("Model", cards.mono(settings["model"])),
            "",
            cards.divider(),
        ]
    )
    await send_card(update, text)


@require_auth
async def cmd_models(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_typing(update, context)
    try:
        data = await cursor(context).list_models()
    except CursorAPIError as e:
        await send_card(
            update,
            cards.error_card(problem="API error", cause=str(e), action="Retry later"),
        )
        return
    models = data.get("models", data if isinstance(data, list) else [])
    if not models:
        await send_card(
            update,
            cards.error_card(
                problem="No models",
                cause="Empty response",
                action="Check API key",
            ),
        )
        return
    lines = [cards.header(subtitle="Models"), ""]
    for m in models[:30]:
        lines.append(f"● {cards.mono(m)}")
    lines.extend(["", cards.divider()])
    await send_card(update, "\n".join(lines))


@require_auth
async def cmd_repos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_typing(update, context)
    try:
        data = await cursor(context).list_repositories()
    except CursorAPIError as e:
        await send_card(
            update,
            cards.error_card(problem="API error", cause=str(e), action="Retry later"),
        )
        return
    repos = data.get("repositories", [])
    if not repos:
        await send_card(
            update,
            cards.error_card(
                problem="No repositories",
                cause="Empty response",
                action="Check GitHub link",
            ),
        )
        return
    lines = [cards.header(subtitle="Repositories"), ""]
    for r in repos[:40]:
        if isinstance(r, dict):
            name = r.get("repository") or r.get("url") or str(r)
        else:
            name = str(r)
        short = name.rstrip("/").split("/")[-2:]
        label = "/".join(short) if len(short) == 2 else name
        lines.append(f"● {cards.esc(label)}")
    lines.extend(["", cards.divider()])
    await send_card(update, "\n".join(lines))


@require_auth
async def cmd_agent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prompt = " ".join(context.args or [])
    if not prompt:
        await send_card(
            update,
            cards.error_card(
                problem="Missing prompt",
                cause="Agent requires instructions",
                action="Send /agent <prompt>",
            ),
        )
        return
    await show_typing(update, context)
    loading = await send_card(
        update, cards.loading_card("Launching", "Provisioning cloud agent.")
    )

    state = context.application.bot_data["state"]
    settings = chat_settings(state, update.effective_chat.id)
    repository = settings.get("repository") or os.environ.get("DEFAULT_REPOSITORY")
    if not repository:
        await send_card(
            update,
            cards.error_card(
                problem="No repository",
                cause="Workspace not configured",
                action="Set one with /repo <url>",
            ),
            edit_message=loading,
        )
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
        await send_card(
            update,
            cards.error_card(
                problem="Launch failed",
                cause=str(e),
                action="Verify API key and repo access",
            ),
            edit_message=loading,
        )
        return

    text = cards.agent_card(agent)
    msg = await send_card(
        update,
        text,
        keyboard=keyboards.agent_actions(agent["id"]),
        edit_message=loading,
    )
    track_console_message(context, msg)
    watch_agent(context, update.effective_chat.id, agent, message_id=msg.message_id)


@require_auth
async def cmd_agents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_typing(update, context)
    try:
        data = await cursor(context).list_agents(limit=10)
    except CursorAPIError as e:
        await send_card(
            update,
            cards.error_card(problem="API error", cause=str(e), action="Retry later"),
        )
        return
    agents = data.get("agents", [])
    if not agents:
        await send_card(
            update,
            cards.error_card(
                problem="No agents",
                cause="Empty list",
                action="Launch with /agent <prompt>",
            ),
        )
        return
    # One card = one decision — show most recent only
    latest = agents[0]
    msg = await send_card(
        update,
        cards.agent_card(latest),
        keyboard=keyboards.agent_actions(str(latest.get("id"))),
    )
    track_console_message(context, msg)


async def _require_id(
    update: Update, context: ContextTypes.DEFAULT_TYPE, usage_action: str
) -> str | None:
    if not context.args:
        await send_card(
            update,
            cards.error_card(
                problem="Missing ID",
                cause="Agent id required",
                action=usage_action,
            ),
        )
        return None
    return context.args[0]


@require_auth
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    agent_id = await _require_id(update, context, "Send /status <agent-id>")
    if not agent_id:
        return
    await show_typing(update, context)
    try:
        agent = await cursor(context).get_agent(agent_id)
    except CursorAPIError as e:
        await send_card(
            update,
            cards.error_card(problem="Lookup failed", cause=str(e), action="Check ID"),
        )
        return
    await send_card(
        update,
        cards.agent_card(agent),
        keyboard=keyboards.agent_actions(agent_id),
    )


@require_auth
async def cmd_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    agent_id = await _require_id(update, context, "Send /conversation <agent-id>")
    if not agent_id:
        return
    await show_typing(update, context)
    try:
        data = await cursor(context).get_conversation(agent_id)
    except CursorAPIError as e:
        await send_card(
            update,
            cards.error_card(problem="Lookup failed", cause=str(e), action="Check ID"),
        )
        return
    messages = data.get("messages", [])
    if not messages:
        await send_card(
            update,
            cards.error_card(
                problem="Empty conversation",
                cause="No messages yet",
                action="Wait or send /followup",
            ),
        )
        return
    last = messages[-1]
    role = last.get("type") or last.get("role") or "message"
    text_body = str(last.get("text") or "")
    if len(text_body) > 800:
        text_body = text_body[:797] + "…"
    body = "\n".join(
        [
            cards.header(agent_id, subtitle="Conversation"),
            "",
            cards.row("Role", cards.esc(role)),
            "",
            cards.row("Latest", cards.esc(text_body)),
            "",
            cards.row("Messages", cards.mono(len(messages))),
            "",
            cards.divider(),
        ]
    )
    await send_card(update, body)


@require_auth
async def cmd_followup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or len(context.args) < 2:
        await send_card(
            update,
            cards.error_card(
                problem="Missing input",
                cause="Need agent id and instructions",
                action="Send /followup <id> <text>",
            ),
        )
        return
    agent_id, text = context.args[0], " ".join(context.args[1:])
    await show_typing(update, context)
    try:
        await cursor(context).add_followup(agent_id, text)
    except CursorAPIError as e:
        await send_card(
            update,
            cards.error_card(problem="Follow-up failed", cause=str(e), action="Retry"),
        )
        return
    loading = await send_card(
        update, cards.loading_card("Dispatching", "Follow-up in flight.")
    )
    body = "\n".join(
        [
            cards.header(agent_id, subtitle="Cloud Agent"),
            cards.status_rail("RUNNING", AGENT_PIPELINE),
            "",
            cards.row("Follow-up", cards.esc(text[:200])),
            "",
            cards.divider(),
        ]
    )
    msg = await send_card(update, body, edit_message=loading)
    watch_agent(
        context,
        update.effective_chat.id,
        {"id": agent_id, "status": "RUNNING"},
        message_id=msg.message_id,
    )


@require_auth
async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    agent_id = await _require_id(update, context, "Send /stop <agent-id>")
    if not agent_id:
        return
    try:
        await cursor(context).stop_agent(agent_id)
    except CursorAPIError as e:
        await send_card(
            update,
            cards.error_card(problem="Stop failed", cause=str(e), action="Retry"),
        )
        return
    await send_card(
        update,
        cards.error_card(
            problem="Stopped",
            cause=f"Agent {agent_id} halted",
            action="No further action",
        ),
    )


@require_auth
async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    agent_id = await _require_id(update, context, "Send /delete <agent-id>")
    if not agent_id:
        return
    try:
        await cursor(context).delete_agent(agent_id)
    except CursorAPIError as e:
        await send_card(
            update,
            cards.error_card(problem="Delete failed", cause=str(e), action="Retry"),
        )
        return
    await send_card(
        update,
        cards.error_card(
            problem="Deleted",
            cause=f"Agent {agent_id} removed",
            action="No further action",
        ),
    )


@require_auth
async def cmd_me(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_typing(update, context)
    try:
        info = await cursor(context).me()
    except CursorAPIError as e:
        await send_card(
            update,
            cards.error_card(problem="API error", cause=str(e), action="Check key"),
        )
        return
    api_key_name = info.get("apiKeyName") or info.get("name") or "—"
    user_email = info.get("userEmail") or info.get("email") or "—"
    text = "\n".join(
        [
            cards.header(subtitle="API Identity"),
            "",
            cards.row("Key", cards.esc(api_key_name)),
            "",
            cards.row("User", cards.esc(user_email)),
            "",
            cards.divider(),
        ]
    )
    await send_card(update, text)


# --- agent callback bridge -----------------------------------------------

async def agent_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    action: str,
    agent_id: str,
) -> None:
    query = update.callback_query
    assert query
    if action == "status":
        try:
            agent = await cursor(context).get_agent(agent_id)
        except CursorAPIError as e:
            await query.edit_message_text(
                cards.error_card(problem="Lookup failed", cause=str(e), action="Retry"),
                parse_mode=ParseMode.HTML,
            )
            return
        await query.edit_message_text(
            cards.agent_card(agent),
            parse_mode=ParseMode.HTML,
            reply_markup=keyboards.agent_actions(agent_id),
            disable_web_page_preview=True,
        )
    elif action == "stop":
        try:
            await cursor(context).stop_agent(agent_id)
        except CursorAPIError as e:
            await query.edit_message_text(
                cards.error_card(problem="Stop failed", cause=str(e), action="Retry"),
                parse_mode=ParseMode.HTML,
            )
            return
        await query.edit_message_text(
            cards.error_card(
                problem="Stopped",
                cause=f"Agent {agent_id} halted",
                action="No further action",
            ),
            parse_mode=ParseMode.HTML,
        )


# --- app lifecycle -------------------------------------------------------

async def on_shutdown(application: Application) -> None:
    client: CursorClient | None = application.bot_data.get("cursor")
    if client:
        await client.close()


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    api_key = os.environ.get("CURSOR_API_KEY", "")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN must be set")
    # Cursor API optional — FinTech console works without it
    if not api_key:
        logger.warning("CURSOR_API_KEY unset — agent commands will fail")

    application = (
        Application.builder().token(token).post_shutdown(on_shutdown).build()
    )
    application.bot_data["cursor"] = CursorClient(api_key or "missing")
    application.bot_data["state"] = load_state()
    application.bot_data["ledger"] = Ledger()
    application.bot_data["agent_callback_handler"] = agent_callback_handler

    command_handlers = {
        "start": cmd_start,
        "help": cmd_start,
        "rates": cmd_rates,
        "usdt": cmd_usdt,
        "ledger": cmd_ledger,
        "history": cmd_history,
        "recent": cmd_recent,
        "void": cmd_void,
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
    for name, fn in command_handlers.items():
        application.add_handler(CommandHandler(name, fn))

    application.add_handler(CallbackQueryHandler(on_callback))
    application.add_handler(MessageHandler(filters.PHOTO, on_photo))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_text)
    )

    logger.info("CE VAULT console starting (polling)")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
