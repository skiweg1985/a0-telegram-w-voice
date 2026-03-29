import asyncio
import json
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager, suppress

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Message as TgMessage, CallbackQuery

from agent import Agent, AgentContext, UserMessage
from helpers import plugins, files, projects
from helpers import message_queue as mq
from helpers.notification import NotificationManager, NotificationType, NotificationPriority
from helpers.persist_chat import save_tmp_chat
from helpers.print_style import PrintStyle
from helpers.errors import format_error
from initialize import initialize_agent

from usr.plugins.telegram_integration_voice.helpers import telegram_client as tc
from usr.plugins.telegram_integration_voice.helpers import speech
from usr.plugins.telegram_integration_voice.helpers.bot_manager import get_bot
from usr.plugins.telegram_integration_voice.helpers.command_registry import format_help_text
from usr.plugins.telegram_integration_voice.helpers.constants import (
    PLUGIN_NAME,
    DOWNLOAD_FOLDER,
    STATE_FILE,
    CTX_TG_BOT,
    CTX_TG_BOT_CFG,
    CTX_TG_CHAT_ID,
    CTX_TG_USER_ID,
    CTX_TG_USERNAME,
    CTX_TG_TYPING_STOP,
    CTX_TG_REPLY_TO,
    CTX_TG_ATTACHMENTS,
    CTX_TG_KEYBOARD,
    CTX_TG_VOICE_REPLY_MODE,
    CTX_TG_FORCE_VOICE_REPLY,
    CTX_TG_LAST_INPUT_WAS_VOICE,
    CTX_TG_TTS_OVERRIDE,
)

# Chat mapping: (bot_name, tg_user_id) → AgentContext ID

_chat_map_lock = threading.Lock()


def _load_state() -> dict:
    path = files.get_abs_path(STATE_FILE)
    if os.path.isfile(path):
        try:
            return json.loads(files.read_file(path))
        except Exception:
            return {}
    return {}


def _save_state(state: dict):
    path = files.get_abs_path(STATE_FILE)
    files.make_dirs(path)
    files.write_file(path, json.dumps(state))


def _map_key(bot_name: str, user_id: int, chat_id: int) -> str:
    return f"{bot_name}:{user_id}:{chat_id}"


def _cmd_rest(message: TgMessage) -> str:
    """Text after the first token of a command (preserves case for project names)."""
    text = (message.text or "").strip()
    if not text:
        return ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return ""
    return parts[1].strip()


def _get_existing_context(message: TgMessage, bot_name: str) -> AgentContext | None:
    user = message.from_user
    if not user:
        return None
    key = _map_key(bot_name, user.id, message.chat.id)
    with _chat_map_lock:
        state = _load_state()
        ctx_id = state.get("chats", {}).get(key)
    if not ctx_id:
        return None
    return AgentContext.get(ctx_id)


def cleanup_old_attachments():
    """Remove downloaded attachment files older than per-bot max age. 0 = keep forever."""
    config = plugins.get_plugin_config(PLUGIN_NAME) or {}
    bots_cfg = config.get("bots") or []
    total_removed = 0
    upload_dir = files.get_abs_path(DOWNLOAD_FOLDER)
    if not os.path.isdir(upload_dir):
        return
    for bot_cfg in bots_cfg:
        bot_name = bot_cfg.get("name", "")
        if not bot_name:
            continue
        max_age_hours = bot_cfg.get("attachment_max_age_hours", 0)
        if not max_age_hours or max_age_hours <= 0:
            continue
        prefix = f"tg_{bot_name}_"
        cutoff = time.time() - max_age_hours * 3600
        for name in os.listdir(upload_dir):
            if not name.startswith(prefix):
                continue
            path = os.path.join(upload_dir, name)
            try:
                if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                    os.remove(path)
                    total_removed += 1
            except OSError:
                pass
    if total_removed:
        PrintStyle.info(f"Telegram: cleaned up {total_removed} old attachment(s)")

# Access control

def _is_allowed(bot_cfg: dict, user_id: int, username: str | None) -> bool:
    allowed = bot_cfg.get("allowed_users") or []
    if not allowed:
        return True  # empty = allow all
    for entry in allowed:
        entry_str = str(entry).strip()
        if entry_str.startswith("@"):
            if username and f"@{username}" == entry_str:
                return True
        else:
            try:
                if int(entry_str) == user_id:
                    return True
            except ValueError:
                if username and entry_str.lower() == username.lower():
                    return True
    return False


def _get_project(bot_cfg: dict, user_id: int) -> str:
    user_projects = bot_cfg.get("user_projects") or {}
    project = user_projects.get(str(user_id), "")
    if not project:
        project = bot_cfg.get("default_project", "")
    return project

# Message handlers (registered with aiogram by bot_manager)

async def handle_start(message: TgMessage, bot_name: str, bot_cfg: dict):
    """Handle /start command."""
    user = message.from_user
    if not user:
        return

    if not _is_allowed(bot_cfg, user.id, user.username):
        await message.reply("You are not authorized to use this bot.")
        return

    instance = get_bot(bot_name)
    if not instance:
        return

    await _send_with_temp_bot(
        instance.bot.token, message.chat.id,
        f"\U0001f44b Hello {user.first_name}! I'm connected to Agent Zero.\n\n"
        "Send me a message and I'll process it.\n"
        "Use /clear to reset the conversation.",
        parse_mode=None,
    )

    # Ensure a chat context exists
    await _get_or_create_context(bot_name, bot_cfg, message)


async def handle_clear(message: TgMessage, bot_name: str, bot_cfg: dict):
    """Handle /clear command — reset user's chat context."""
    user = message.from_user
    if not user:
        return

    if not _is_allowed(bot_cfg, user.id, user.username):
        return

    key = _map_key(bot_name, user.id, message.chat.id)

    with _chat_map_lock:
        state = _load_state()
        ctx_id = state.get("chats", {}).get(key)
        if ctx_id:
            ctx = AgentContext.get(ctx_id)
            if ctx:
                ctx.reset()
                ctx.data.pop(CTX_TG_TTS_OVERRIDE, None)
                PrintStyle.info(f"Telegram ({bot_name}): cleared chat for user {user.id}")

    instance = get_bot(bot_name)
    if instance:
        await _send_with_temp_bot(
            instance.bot.token, message.chat.id,
            "Chat cleared. Send a new message to start fresh.",
            parse_mode=None,
        )

    # Send notification
    if bot_cfg.get("notify_messages", False):
        username_str = f"@{user.username}" if user.username else str(user.id)
        NotificationManager.send_notification(
            type=NotificationType.INFO,
            priority=NotificationPriority.NORMAL,
            title="Telegram: chat cleared",
            message=f"{username_str} cleared their chat via /clear",
            display_time=5,
            group="telegram",
        )


async def handle_help(message: TgMessage, bot_name: str, bot_cfg: dict):
    """Handle /help — list commands."""
    user = message.from_user
    if not user or not _is_allowed(bot_cfg, user.id, user.username):
        return
    instance = get_bot(bot_name)
    if not instance:
        return
    await _send_with_temp_bot(
        instance.bot.token,
        message.chat.id,
        format_help_text(),
        parse_mode=None,
    )


async def handle_tts(message: TgMessage, bot_name: str, bot_cfg: dict):
    """Handle /tts — per-session voice reply override."""
    user = message.from_user
    if not user or not _is_allowed(bot_cfg, user.id, user.username):
        return
    ctx = await _get_or_create_context(bot_name, bot_cfg, message)
    if not ctx:
        return
    instance = get_bot(bot_name)
    if not instance:
        return

    arg = _cmd_rest(message).lower().strip()
    if not arg:
        cur = ctx.data.get(CTX_TG_TTS_OVERRIDE)
        if cur == "off":
            ctx.data.pop(CTX_TG_TTS_OVERRIDE, None)
            reply = "Voice replies: follow plugin config (unmuted)."
        else:
            ctx.data[CTX_TG_TTS_OVERRIDE] = "off"
            reply = "Voice replies: muted for this session."
    elif arg in ("on", "enable"):
        ctx.data.pop(CTX_TG_TTS_OVERRIDE, None)
        reply = "Voice replies: follow plugin config."
    elif arg in ("off", "disable"):
        ctx.data[CTX_TG_TTS_OVERRIDE] = "off"
        reply = "Voice replies: off for this session."
    elif arg == "auto":
        ctx.data[CTX_TG_TTS_OVERRIDE] = "auto"
        reply = "Voice mode: auto (reply with voice only after voice input)."
    elif arg == "force":
        ctx.data[CTX_TG_TTS_OVERRIDE] = "force"
        reply = "Voice mode: force (voice replies when TTS is enabled)."
    else:
        reply = "Usage: /tts or /tts on|off|auto|force"

    save_tmp_chat(ctx)
    await _send_with_temp_bot(instance.bot.token, message.chat.id, reply, parse_mode=None)


async def handle_status(message: TgMessage, bot_name: str, bot_cfg: dict):
    """Handle /status — model, tokens, project, TTS/STT, run state."""
    user = message.from_user
    if not user or not _is_allowed(bot_cfg, user.id, user.username):
        return
    instance = get_bot(bot_name)
    if not instance:
        return

    ctx = _get_existing_context(message, bot_name)
    lines: list[str] = ["Agent status", ""]

    chat_cfg: dict = {}
    util_cfg: dict = {}
    try:
        from plugins._model_config.helpers import model_config as mc

        ag = ctx.agent0 if ctx else None
        chat_cfg = mc.get_chat_model_config(ag)
        util_cfg = mc.get_utility_model_config(ag)
    except Exception:
        pass

    chat_provider = str(chat_cfg.get("provider", "") or "?")
    chat_name = str(chat_cfg.get("name", "") or "?")
    util_provider = str(util_cfg.get("provider", "") or "?")
    util_name = str(util_cfg.get("name", "") or "?")
    ctx_len = int(chat_cfg.get("ctx_length", 0) or 0)
    ctx_hist = float(chat_cfg.get("ctx_history", 0.7) or 0.7)
    hist_limit = int(ctx_len * ctx_hist) if ctx_len else 0

    lines.append(f"Model: {chat_provider} / {chat_name}")
    lines.append(f"Utility: {util_provider} / {util_name}")

    if ctx:
        agent = ctx.agent0
        hist_tokens = agent.history.get_tokens()
        ctx_window = agent.get_data(Agent.DATA_NAME_CTX_WINDOW) or {}
        win_tokens = int((ctx_window.get("tokens") or 0))
        pct = (100.0 * hist_tokens / hist_limit) if hist_limit else 0.0
        lines.append(
            f"History: ~{hist_tokens} / ~{hist_limit} tokens ({pct:.1f}% of history budget)"
        )
        lines.append(f"Last prompt window: ~{win_tokens} tokens (approx.)")
        lines.append(f"Messages (counter): {agent.history.counter}")
        proj = projects.get_context_project_name(ctx)
        lines.append(f"Project: {proj or '(none)'}")
        sess = ctx.data.get(CTX_TG_TTS_OVERRIDE)
        sess_lbl = "plugin default" if sess is None else str(sess)
        lines.append(
            f"TTS engine: {'on' if speech.tts_enabled(bot_cfg) else 'off'}; session voice: {sess_lbl}"
        )
        lines.append(f"STT: {'on' if speech.stt_enabled(bot_cfg) else 'off'}")
        lines.append(f"Running: {ctx.is_running()}; Paused: {ctx.paused}")
        lines.append(f"Context id: {ctx.id}")
    else:
        lines.append("No Telegram session yet — send a message or /start.")
        lines.append(f"TTS engine: {'on' if speech.tts_enabled(bot_cfg) else 'off'}")
        lines.append(f"STT: {'on' if speech.stt_enabled(bot_cfg) else 'off'}")

    text = "\n".join(lines)
    await _send_with_temp_bot(instance.bot.token, message.chat.id, text, parse_mode=None)


async def handle_compact(message: TgMessage, bot_name: str, bot_cfg: dict):
    """Handle /compact — compress conversation history."""
    user = message.from_user
    if not user or not _is_allowed(bot_cfg, user.id, user.username):
        return
    ctx = await _get_or_create_context(bot_name, bot_cfg, message)
    if not ctx:
        return
    instance = get_bot(bot_name)
    if not instance:
        return

    try:
        changed = await ctx.agent0.history.compress()
        save_tmp_chat(ctx)
        reply = (
            "Context compressed (summaries/truncations applied)."
            if changed
            else "Nothing to compress right now."
        )
    except Exception as e:
        reply = f"Compress failed: {format_error(e)}"
        PrintStyle.error(f"Telegram /compact: {format_error(e)}")

    await _send_with_temp_bot(instance.bot.token, message.chat.id, reply, parse_mode=None)


async def handle_stop(message: TgMessage, bot_name: str, bot_cfg: dict):
    """Handle /stop — kill running agent task."""
    user = message.from_user
    if not user or not _is_allowed(bot_cfg, user.id, user.username):
        return
    ctx = _get_existing_context(message, bot_name)
    instance = get_bot(bot_name)
    if not instance:
        return
    if not ctx:
        await _send_with_temp_bot(
            instance.bot.token,
            message.chat.id,
            "No active session.",
            parse_mode=None,
        )
        return
    ctx.kill_process()
    save_tmp_chat(ctx)
    await _send_with_temp_bot(
        instance.bot.token,
        message.chat.id,
        "Stopped the running task (if any).",
        parse_mode=None,
    )


async def handle_pause(message: TgMessage, bot_name: str, bot_cfg: dict):
    user = message.from_user
    if not user or not _is_allowed(bot_cfg, user.id, user.username):
        return
    ctx = await _get_or_create_context(bot_name, bot_cfg, message)
    if not ctx:
        return
    instance = get_bot(bot_name)
    if not instance:
        return
    ctx.paused = True
    save_tmp_chat(ctx)
    await _send_with_temp_bot(
        instance.bot.token,
        message.chat.id,
        "Agent paused. Use /resume to continue.",
        parse_mode=None,
    )


async def handle_resume(message: TgMessage, bot_name: str, bot_cfg: dict):
    user = message.from_user
    if not user or not _is_allowed(bot_cfg, user.id, user.username):
        return
    ctx = _get_existing_context(message, bot_name)
    instance = get_bot(bot_name)
    if not instance:
        return
    if not ctx:
        await _send_with_temp_bot(
            instance.bot.token,
            message.chat.id,
            "No active session.",
            parse_mode=None,
        )
        return
    ctx.paused = False
    save_tmp_chat(ctx)
    await _send_with_temp_bot(
        instance.bot.token,
        message.chat.id,
        "Agent resumed.",
        parse_mode=None,
    )


async def handle_project(message: TgMessage, bot_name: str, bot_cfg: dict):
    user = message.from_user
    if not user or not _is_allowed(bot_cfg, user.id, user.username):
        return
    ctx = await _get_or_create_context(bot_name, bot_cfg, message)
    if not ctx:
        return
    instance = get_bot(bot_name)
    if not instance:
        return

    arg = _cmd_rest(message).strip()
    if not arg:
        active = projects.get_context_project_name(ctx)
        names = [p["name"] for p in projects.get_active_projects_list()]
        reply = "\n".join(
            [
                f"Active project: {active or '(none)'}",
                "Available: " + (", ".join(names) if names else "(none)"),
                "Usage: /project <name>",
            ]
        )
    else:
        names = {p["name"] for p in projects.get_active_projects_list()}
        if arg not in names:
            reply = f"Unknown project: {arg}. Use /project to list."
        else:
            try:
                projects.activate_project(ctx.id, arg)
                save_tmp_chat(ctx)
                reply = f"Switched project to: {arg}"
            except Exception as e:
                reply = f"Failed to switch project: {format_error(e)}"

    await _send_with_temp_bot(instance.bot.token, message.chat.id, reply, parse_mode=None)


async def handle_model(message: TgMessage, bot_name: str, bot_cfg: dict):
    user = message.from_user
    if not user or not _is_allowed(bot_cfg, user.id, user.username):
        return
    ctx = await _get_or_create_context(bot_name, bot_cfg, message)
    if not ctx:
        return
    instance = get_bot(bot_name)
    if not instance:
        return

    try:
        from plugins._model_config.helpers import model_config as mc
    except Exception:
        await _send_with_temp_bot(
            instance.bot.token,
            message.chat.id,
            "Model presets require the _model_config plugin.",
            parse_mode=None,
        )
        return

    arg = _cmd_rest(message).strip()
    if not arg:
        chat_cfg = mc.get_chat_model_config(ctx.agent0)
        lines = [
            f"Chat model: {chat_cfg.get('provider', '?')} / {chat_cfg.get('name', '?')}",
            f"Override allowed: {mc.is_chat_override_allowed(ctx.agent0)}",
        ]
        presets = mc.get_presets()
        if presets:
            lines.append("Presets: " + ", ".join(str(p.get("name", "")) for p in presets if p.get("name")))
        reply = "\n".join(lines)
    else:
        if not mc.is_chat_override_allowed(ctx.agent0):
            reply = "Per-chat model override is disabled (allow_chat_override in _model_config)."
        else:
            arg_key = arg.strip().lower()
            preset = None
            for p in mc.get_presets():
                pn = p.get("name")
                if pn and str(pn).strip().lower() == arg_key:
                    preset = p
                    break
            if not preset:
                plist = [str(p.get("name", "")) for p in mc.get_presets() if p.get("name")]
                reply = f"Unknown preset {arg!r}. Known: {', '.join(plist) or '(none)'}"
            else:
                pname = preset.get("name")
                ctx.set_data("chat_model_override", {"preset_name": pname})
                save_tmp_chat(ctx)
                reply = f"Model preset set to: {pname}"

    await _send_with_temp_bot(instance.bot.token, message.chat.id, reply, parse_mode=None)


async def handle_message(message: TgMessage, bot_name: str, bot_cfg: dict):
    """Handle incoming user message."""
    user = message.from_user
    if not user:
        return

    if not _is_allowed(bot_cfg, user.id, user.username):
        return

    instance = get_bot(bot_name)
    if not instance:
        return

    # Start persistent typing indicator (thread-based, works across event loops)
    typing_stop = _start_typing(instance.bot.token, message.chat.id)

    # Get or create agent context
    context = await _get_or_create_context(bot_name, bot_cfg, message)
    if not context:
        typing_stop.set()
        await _send_with_temp_bot(
            instance.bot.token, message.chat.id,
            "Failed to create chat session.",
            parse_mode=None,
        )
        return

    # Store stop event so send_telegram_reply can cancel typing
    context.data[CTX_TG_TYPING_STOP] = typing_stop

    # In group chats, if user replied to the bot's message, reply to the user's message
    reply_to_id = None
    if message.chat.type != "private" and instance.bot_info:
        if (message.reply_to_message
                and message.reply_to_message.from_user
                and message.reply_to_message.from_user.id == instance.bot_info.id):
            reply_to_id = message.message_id
    context.data[CTX_TG_REPLY_TO] = reply_to_id

    # Build user message text
    text = _extract_message_content(message)
    is_voice_input = _message_has_voice_input(message)
    context.data[CTX_TG_LAST_INPUT_WAS_VOICE] = is_voice_input

    # Use temp bot for downloads (cross-event-loop safe)
    async with _temp_bot(instance.bot.token) as dl_bot:
        attachments = await _download_attachments(dl_bot, message, bot_name=bot_name)

    # Optional STT for voice/audio inputs
    if is_voice_input and speech.stt_enabled(bot_cfg):
        audio_ref = _pick_audio_attachment(attachments)
        if audio_ref:
            audio_path = files.fix_dev_path(audio_ref)
            try:
                stt_result = await asyncio.to_thread(speech.transcribe_audio_file, bot_cfg, audio_path)
                transcript = str((stt_result or {}).get("text") or "").strip()
                if transcript:
                    text = _merge_voice_transcript(text, transcript)
                else:
                    text = text + "\n[Voice transcript unavailable: empty result]"
            except Exception as e:
                PrintStyle.error(f"Telegram STT failed: {format_error(e)}")
                text = text + f"\n[Voice transcript failed: {format_error(e)}]"

    # Build user message with prompt
    agent = context.agent0
    user_msg = agent.read_prompt(
        "fw.telegram.user_message.md",
        sender=_format_user(user),
        body=text,
    )

    msg_id = str(uuid.uuid4())
    mq.log_user_message(context, user_msg, attachments, message_id=msg_id, source=" (telegram)")
    context.communicate(UserMessage(
        message=user_msg,
        attachments=attachments,
        id=msg_id,
    ))

    save_tmp_chat(context)

    # Send notification
    if bot_cfg.get("notify_messages", False):
        username_str = f"@{user.username}" if user.username else str(user.id)
        preview = (text[:80] + "...") if len(text) > 80 else text
        NotificationManager.send_notification(
            type=NotificationType.INFO,
            priority=NotificationPriority.HIGH,
            title="Telegram: new message",
            message=f"From {username_str}: {preview}",
            display_time=10,
            group="telegram",
        )


async def handle_callback_query(query: CallbackQuery, bot_name: str, bot_cfg: dict):
    """Handle inline keyboard button press."""
    user = query.from_user
    if not user or not query.message:
        return

    if not _is_allowed(bot_cfg, user.id, user.username):
        await query.answer("Not authorized.")
        return

    await query.answer()

    # Treat callback data as a user message
    text = query.data or ""
    if not text:
        return

    context = await _get_or_create_context_from_user(
        bot_name, bot_cfg, user.id, user.username, query.message.chat.id,
    )
    if not context:
        return

    agent = context.agent0
    user_msg = agent.read_prompt(
        "fw.telegram.user_message.md",
        sender=_format_user(user),
        body=f"[Button pressed: {text}]",
    )

    msg_id = str(uuid.uuid4())
    mq.log_user_message(context, user_msg, [], message_id=msg_id, source=" (telegram)")
    context.communicate(UserMessage(message=user_msg, id=msg_id))
    save_tmp_chat(context)


async def handle_new_members(message: TgMessage, bot_name: str, bot_cfg: dict):
    """Send welcome message when new members join a group."""
    if not bot_cfg.get("welcome_enabled", False):
        return

    new_members = message.new_chat_members or []
    if not new_members:
        return

    instance = get_bot(bot_name)
    if not instance:
        return

    template = bot_cfg.get("welcome_message", "").strip()
    if not template:
        template = "Welcome, {name}!"

    for member in new_members:
        if member.is_bot:
            continue
        name = member.full_name or member.first_name or str(member.id)
        text = template.replace("{name}", name)
        await _send_with_temp_bot(instance.bot.token, message.chat.id, text, parse_mode=None)

# Context management

async def _get_or_create_context(
    bot_name: str,
    bot_cfg: dict,
    message: TgMessage,
) -> AgentContext | None:
    user = message.from_user
    if not user:
        return None
    return await _get_or_create_context_from_user(
        bot_name, bot_cfg, user.id, user.username, message.chat.id,
    )


async def _get_or_create_context_from_user(
    bot_name: str,
    bot_cfg: dict,
    user_id: int,
    username: str | None,
    chat_id: int,
) -> AgentContext | None:
    key = _map_key(bot_name, user_id, chat_id)

    with _chat_map_lock:
        state = _load_state()
        chats = state.setdefault("chats", {})
        ctx_id = chats.get(key)

        # Check if existing context is still alive
        if ctx_id:
            ctx = AgentContext.get(ctx_id)
            if ctx:
                return ctx
            # Context was garbage collected, remove stale mapping
            chats.pop(key, None)

        # Create new context
        try:
            config = initialize_agent()
            display_name = f"@{username}" if username else str(user_id)
            ctx = AgentContext(config, name=f"Telegram: {display_name}")

            ctx.data[CTX_TG_BOT] = bot_name
            ctx.data[CTX_TG_BOT_CFG] = bot_cfg
            ctx.data[CTX_TG_CHAT_ID] = chat_id
            ctx.data[CTX_TG_USER_ID] = user_id
            ctx.data[CTX_TG_USERNAME] = username or ""

            project = _get_project(bot_cfg, user_id)
            if project:
                projects.activate_project(ctx.id, project)

            # Inherit model override from an existing context in the same project
            _inherit_model_override(ctx)

            chats[key] = ctx.id
            _save_state(state)

            PrintStyle.success(
                f"Telegram ({bot_name}): new chat {ctx.id} for user {display_name}"
            )
            return ctx

        except Exception as e:
            PrintStyle.error(f"Telegram: failed to create context: {format_error(e)}")
            return None

# Message content extraction

def _extract_message_content(message: TgMessage) -> str:
    parts = []

    if message.text:
        parts.append(message.text)
    elif message.caption:
        parts.append(message.caption)

    if message.location:
        loc = message.location
        parts.append(f"[Location: {loc.latitude}, {loc.longitude}]")

    if message.contact:
        c = message.contact
        parts.append(f"[Contact: {c.first_name} {c.last_name or ''} phone={c.phone_number}]")

    if message.sticker:
        parts.append(f"[Sticker: {message.sticker.emoji or ''}]")

    # Simple attachment indicators
    for attr, label in [("voice", "Voice message"), ("video_note", "Video note")]:
        if getattr(message, attr, None):
            parts.append(f"[{label} — see attachment]")

    return "\n".join(parts) if parts else "[No text content]"


def _message_has_voice_input(message: TgMessage) -> bool:
    return bool(message.voice or message.audio or message.video_note)


def _pick_audio_attachment(attachments: list[str]) -> str | None:
    if not attachments:
        return None
    prioritized = ["voice_", "audio_", "videonote_"]
    low = [a.lower() for a in attachments]
    for needle in prioritized:
        for idx, item in enumerate(low):
            if needle in item:
                return attachments[idx]

    # fallback by extension
    for path in attachments:
        p = path.lower()
        if p.endswith((".ogg", ".mp3", ".wav", ".m4a", ".mp4")):
            return path
    return attachments[0]


def _merge_voice_transcript(original_text: str, transcript: str) -> str:
    original = (original_text or "").strip()
    if original in ("", "[No text content]", "[Voice message — see attachment]", "[Video note — see attachment]"):
        return f"[Voice transcript]\n{transcript}"
    return f"{original}\n\n[Voice transcript]\n{transcript}"


async def _download_attachments(bot, message: TgMessage, bot_name: str = "") -> list[str]:
    """Download photos, documents, audio, voice, video from message."""
    paths: list[str] = []
    tg_prefix = f"tg_{bot_name}_" if bot_name else "tg_"
    # Host-local path for actual file I/O
    download_dir = files.get_abs_path(DOWNLOAD_FOLDER)
    os.makedirs(download_dir, exist_ok=True)
    # Docker-style path for agent references
    download_dir_ref = files.get_abs_path_dockerized(DOWNLOAD_FOLDER)

    async def _dl(file_id: str, filename: str) -> str | None:
        safe_name = f"{tg_prefix}{uuid.uuid4().hex[:8]}_{filename}"
        dest = os.path.join(download_dir, safe_name)
        result = await tc.download_file(bot, file_id, dest)
        if result:
            return os.path.join(download_dir_ref, safe_name)
        return None

    # Photo: get largest resolution
    if message.photo:
        photo = message.photo[-1]
        path = await _dl(photo.file_id, f"photo_{photo.file_unique_id}.jpg")
        if path:
            paths.append(path)

    # Other attachment types: (attr, default_prefix, default_ext)
    _types = [
        ("document",   "file",      None),
        ("audio",      "audio",     ".mp3"),
        ("voice",      "voice",     ".ogg"),
        ("video",      "video",     ".mp4"),
        ("video_note", "videonote", ".mp4"),
    ]
    for attr, prefix, ext in _types:
        obj = getattr(message, attr, None)
        if not obj:
            continue
        fname = getattr(obj, "file_name", None) or f"{prefix}_{obj.file_unique_id}{ext or ''}"
        path = await _dl(obj.file_id, fname)
        if path:
            paths.append(path)

    return paths

# Reply sending (called from process_chain_end extension)

async def send_telegram_reply(
    context: AgentContext,
    response_text: str,
    attachments: list[str] | None = None,
    keyboard: list[list[dict]] | None = None,
) -> str | None:
    """Send reply to Telegram user. Returns error string or None on success."""
    bot_name = context.data.get(CTX_TG_BOT)
    if not bot_name:
        return "No Telegram bot configured on context"

    instance = get_bot(bot_name)
    if not instance:
        return f"Bot '{bot_name}' not running"

    chat_id = context.data.get(CTX_TG_CHAT_ID)
    if not chat_id:
        return "No chat_id on context"

    bot_cfg = context.data.get(CTX_TG_BOT_CFG, {}) or {}
    reply_cfg = speech.voice_reply_settings(bot_cfg)

    # Optional per-response overrides captured by tool_execute_after extension
    override_mode = str(context.data.pop(CTX_TG_VOICE_REPLY_MODE, "") or "").lower()
    forced_flag = bool(context.data.pop(CTX_TG_FORCE_VOICE_REPLY, False))

    mode = str(override_mode if override_mode in {"off", "auto", "force"} else reply_cfg["voice_mode"]).lower()
    if forced_flag:
        mode = "force"

    session_voice = context.data.get(CTX_TG_TTS_OVERRIDE)
    if session_voice == "off":
        mode = "off"
    elif session_voice == "force":
        mode = "force"
    elif session_voice == "auto":
        mode = "auto"

    last_input_was_voice = bool(context.data.get(CTX_TG_LAST_INPUT_WAS_VOICE, False))
    want_voice = mode == "force" or (mode == "auto" and last_input_was_voice)

    reply_to = context.data.get(CTX_TG_REPLY_TO)

    tts_on = speech.tts_enabled(bot_cfg)
    if want_voice and response_text and not tts_on:
        PrintStyle.info(
            "Telegram TTS skipped: speech.tts.enabled is false for this bot (check plugin config / project scope)."
        )
    elif want_voice and not response_text:
        PrintStyle.info("Telegram TTS skipped: empty response text.")
    elif (
        not want_voice
        and mode == "auto"
        and response_text
        and tts_on
        and not last_input_was_voice
    ):
        PrintStyle.info(
            "Telegram TTS skipped: voice_mode=auto (send a voice message to get a voice reply, or set reply.voice_mode to force)."
        )

    try:
        async with _temp_bot(instance.bot.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML)) as reply_bot:
            if attachments:
                for path in attachments:
                    local_path = files.fix_dev_path(path)
                    if tc.is_image_file(local_path):
                        await tc.send_photo(reply_bot, chat_id, local_path, reply_to_message_id=reply_to)
                    else:
                        await tc.send_file(reply_bot, chat_id, local_path, reply_to_message_id=reply_to)

            sent_voice = False
            voice_file: str | None = None
            if want_voice and response_text and tts_on:
                try:
                    max_chars = max(100, int(reply_cfg["max_chars"]))
                    voice_text = response_text[:max_chars]
                    await tc.send_record_voice(reply_bot, chat_id)
                    voice_file, _meta = await asyncio.to_thread(speech.synthesize_to_voice_file, bot_cfg, voice_text)
                    msg_id = await tc.send_voice(reply_bot, chat_id, voice_file, reply_to_message_id=reply_to)
                    sent_voice = bool(msg_id)
                    if sent_voice:
                        PrintStyle.info(
                            f"Telegram TTS: voice message sent (bot={bot_name!r}, mode={mode!r})."
                        )
                except Exception as e:
                    PrintStyle.error(f"Telegram TTS failed: {format_error(e)}")
                finally:
                    if voice_file:
                        with suppress(Exception):
                            os.remove(voice_file)

            should_send_text = bool(response_text) and (keyboard is not None or not sent_voice or reply_cfg["also_send_text"])
            if should_send_text:
                html_text = tc.md_to_telegram_html(response_text)
                if keyboard:
                    await tc.send_text_with_keyboard(reply_bot, chat_id, html_text, keyboard, reply_to_message_id=reply_to)
                else:
                    await tc.send_text(reply_bot, chat_id, html_text, reply_to_message_id=reply_to)

        return None

    except Exception as e:
        error = format_error(e)
        PrintStyle.error(f"Telegram reply failed: {error}")
        return error

# Helpers

@asynccontextmanager
async def _temp_bot(token: str, **kwargs):
    """Create a temporary Bot, yield it, and ensure the session is closed."""
    bot = Bot(token=token, **kwargs)
    try:
        yield bot
    finally:
        with suppress(Exception):
            await bot.session.close()


async def _send_with_temp_bot(token: str, chat_id: int, text: str, parse_mode: str | None = None):
    """Send text using a temporary Bot to avoid cross-event-loop session issues."""
    async with _temp_bot(token) as bot:
        await tc.send_text(bot, chat_id, text, parse_mode=parse_mode)


def _start_typing(token: str, chat_id: int) -> threading.Event:
    """Spawn a daemon thread that sends typing every 4s. Returns a stop Event."""
    stop = threading.Event()

    def _run():
        import asyncio

        async def _loop():
            async with _temp_bot(token) as bot:
                while not stop.is_set():
                    await tc.send_typing(bot, chat_id)
                    for _ in range(8):
                        if stop.is_set():
                            return
                        await asyncio.sleep(0.5)

        try:
            asyncio.run(_loop())
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()
    return stop


def _format_user(user) -> str:
    name = user.first_name or ""
    if user.last_name:
        name += f" {user.last_name}"
    if user.username:
        name += f" (@{user.username})"
    return name.strip() or str(user.id)


def _inherit_model_override(ctx: AgentContext):
    """Copy chat_model_override from the most recent sibling context in the same project."""
    project = ctx.get_data("project")
    if not project:
        return
    try:
        from plugins._model_config.helpers.model_config import is_chat_override_allowed
        if not is_chat_override_allowed(ctx.agent0):
            return
    except Exception:
        return
    source = max(
        (c for c in AgentContext.all()
         if c.id != ctx.id and c.get_data("project") == project and c.get_data("chat_model_override")),
        key=lambda c: c.last_message,
        default=None,
    )
    if source:
        ctx.set_data("chat_model_override", source.get_data("chat_model_override"))
