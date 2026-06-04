import asyncio
import hashlib
import html
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime
from contextlib import asynccontextmanager, suppress

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Message as TgMessage, CallbackQuery

from agent import Agent, AgentContext, UserMessage
from helpers import plugins, files, projects
from helpers import message_queue as mq
from helpers.notification import NotificationManager, NotificationType, NotificationPriority
from helpers.persist_chat import save_tmp_chat, _deserialize_context
from helpers.print_style import PrintStyle
from helpers.errors import format_error
from initialize import initialize_agent

from usr.plugins.telegram_integration_voice.helpers import telegram_client as tc
from usr.plugins.telegram_integration_voice.helpers import detail_status, speech
from usr.plugins.telegram_integration_voice.helpers.bot_manager import get_bot
from usr.plugins.telegram_integration_voice.helpers.command_registry import format_help_text
from usr.plugins.telegram_integration_voice.helpers.constants import (
    PLUGIN_NAME,
    DOWNLOAD_FOLDER,
    STATE_FILE,
    PERSISTED_CHATS_FOLDER,
    PERSISTED_CHAT_FILE_NAME,
    CTX_TG_BOT,
    CTX_TG_BOT_CFG,
    CTX_TG_CHAT_ID,
    CTX_TG_USER_ID,
    CTX_TG_USERNAME,
    CTX_TG_TYPING_STOP,
    CTX_TG_REPLY_TO,
    CTX_TG_REPLY_CONTEXT,
    CTX_TG_ATTACHMENTS,
    CTX_TG_KEYBOARD,
    CTX_TG_VOICE_REPLY_MODE,
    CTX_TG_FORCE_VOICE_REPLY,
    CTX_TG_LAST_INPUT_WAS_VOICE,
    CTX_TG_PROGRESS_MESSAGE_ID,
    CTX_TG_PROGRESS_LAST_HASH,
    CTX_TG_PROGRESS_LAST_TS,
    CTX_TG_PROGRESS_LINES,
    CTX_TG_PROGRESS_HEADER,
    CTX_TG_STREAM_PREVIEW,
    CTX_TG_STREAM_ACTIVE,
    CTX_TG_STREAM_DRAFT_ID,
    CTX_TG_STREAM_DRAFT_LAST_TS,
    CTX_TG_STREAM_DRAFT_ACTIVE,
    CTX_TG_STREAM_DRAFT_USED,
    CTX_TG_STREAM_DRAFT_DISABLED,
    CTX_TG_LAST_TEXT_RESPONSE,
    CTX_TG_LAST_TEXT_RESPONSE_TOKEN,
    CTX_TG_TTS_OVERRIDE,
    CTX_TG_VOICE_CONVERSATION_MODE,
    CTX_TG_OUTPUT_OPTIMIZE,
    CTX_TG_VOICE_TEXT,
    CTX_TG_DETAIL_LEVEL_SESSION,
    CTX_TG_DETAIL_LAST_SENT_TS,
    CTX_TG_ALSO_SEND_TEXT_OVERRIDE,
    TG_UI_CALLBACK_PREFIX,
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


def _parse_plugin_ui_callback(data: str) -> tuple[str, str] | None:
    """Parse tgx|<kind>|<payload> (plugin UI). Returns (kind, payload) or None."""
    if not data or not data.startswith(TG_UI_CALLBACK_PREFIX):
        return None
    rest = data[len(TG_UI_CALLBACK_PREFIX) :]
    if "|" not in rest:
        return None
    kind, payload = rest.split("|", 1)
    if not kind or not payload:
        return None
    return kind, payload


def _optimize_output_inline_keyboard() -> list[list[dict]]:
    p = TG_UI_CALLBACK_PREFIX
    return [
        [
            {"text": "Auto", "callback_data": f"{p}o|auto"},
            {"text": "Voice", "callback_data": f"{p}o|voice"},
            {"text": "Text", "callback_data": f"{p}o|text"},
        ],
        [
            {"text": "Off", "callback_data": f"{p}o|off"},
            {"text": "Reset", "callback_data": f"{p}o|reset"},
        ],
    ]


def _model_preset_button_label(name: str) -> str:
    """Telegram inline button text limit 64 chars."""
    n = str(name).strip()
    if len(n) <= 60:
        return n
    return n[:57] + "…"


def _tts_inline_keyboard() -> list[list[dict]]:
    """Session voice: plugin default, muted, auto, force."""
    p = TG_UI_CALLBACK_PREFIX
    return [
        [
            {"text": "Default", "callback_data": f"{p}t|on"},
            {"text": "Muted", "callback_data": f"{p}t|off"},
        ],
        [
            {"text": "Auto", "callback_data": f"{p}t|auto"},
            {"text": "Force", "callback_data": f"{p}t|force"},
        ],
    ]


def _voice_mode_inline_keyboard() -> list[list[dict]]:
    p = TG_UI_CALLBACK_PREFIX
    return [
        [
            {"text": "🎙 Voice only", "callback_data": f"{p}v|voice_only"},
            {"text": "🎙+📝 Voice + Text", "callback_data": f"{p}v|voice_text"},
        ],
        [
            {"text": "📝 Text only", "callback_data": f"{p}v|text_only"},
            {"text": "⏹ Off", "callback_data": f"{p}v|off"},
        ],
    ]


def _show_text_quick_action_keyboard(token: str) -> list[list[dict]]:
    p = TG_UI_CALLBACK_PREFIX
    return [[{"text": "📝 Text anzeigen", "callback_data": f"{p}qa|show_text:{token}"}]]


def _append_inline_keyboard(
    base: list[list[dict]] | None,
    extra: list[list[dict]] | None,
) -> list[list[dict]] | None:
    rows = list(base or [])
    if extra:
        rows.extend(extra)
    return rows or None


def _voice_conversation_mode(ctx: AgentContext) -> str:
    return str(ctx.data.get(CTX_TG_VOICE_CONVERSATION_MODE, "off") or "off").strip().lower()


def _voice_mode_label(mode: str) -> str:
    return {
        "voice_only": "voice only",
        "voice_text": "voice + text",
        "text_only": "text only",
        "off": "off",
    }.get(str(mode or "off").strip().lower(), "off")


def _voice_mode_header(ctx: AgentContext) -> str:
    mode = _voice_conversation_mode(ctx)
    if mode == "off":
        return "🎙 Voice Mode: off"
    return f"🎙 Voice Mode Active: {_voice_mode_label(mode)}"


def _apply_voice_mode_setting(ctx: AgentContext, mode: str) -> str:
    mode = str(mode or "").strip().lower()
    if mode in ("start", "on", "enable"):
        mode = "voice_text"
    if mode not in ("off", "voice_only", "voice_text", "text_only"):
        return "Usage: /voice [voice_only|voice_text|text_only|off]"
    ctx.data[CTX_TG_VOICE_CONVERSATION_MODE] = mode
    if mode == "off":
        return "🎙 Voice mode off. Session uses normal TTS/text settings again."
    return f"🎙 Voice mode active: {_voice_mode_label(mode)}."


def _tts_session_description(ctx: AgentContext, bot_cfg: dict) -> str:
    return speech.effective_voice_reply_mode(bot_cfg, ctx.data)


def _apply_tts_setting(ctx: AgentContext, mode: str, bot_cfg: dict) -> str:
    """Apply on|off|auto|force (mutates ctx.data). Returns user-facing reply."""
    mode = mode.strip().lower()
    if mode in ("on", "enable"):
        ctx.data.pop(CTX_TG_TTS_OVERRIDE, None)
        eff = speech.effective_voice_reply_mode(bot_cfg, ctx.data)
        return f"Voice replies: {eff}."
    if mode in ("off", "disable"):
        ctx.data[CTX_TG_TTS_OVERRIDE] = "off"
        return "Voice replies: off."
    if mode == "auto":
        ctx.data[CTX_TG_TTS_OVERRIDE] = "auto"
        return "Voice replies: auto."
    if mode == "force":
        ctx.data[CTX_TG_TTS_OVERRIDE] = "force"
        return "Voice replies: force."
    return "Usage: /tts on|off|auto|force"


def _detail_inline_keyboard() -> list[list[dict]]:
    p = TG_UI_CALLBACK_PREFIX
    return [
        [
            {"text": "Off", "callback_data": f"{p}d|off"},
            {"text": "Info", "callback_data": f"{p}d|info"},
        ],
        [
            {"text": "Verbose", "callback_data": f"{p}d|debug"},
            {"text": "Reset", "callback_data": f"{p}d|reset"},
        ],
    ]


def _detail_session_description(ctx: AgentContext, bot_cfg: dict) -> str:
    eff = detail_status.effective_detail_level(bot_cfg, ctx.data)
    return detail_status.detail_level_display(eff)


def _apply_detail_level(ctx: AgentContext, bot_cfg: dict, arg: str) -> str:
    arg = arg.strip().lower()
    if arg == "verbose":
        arg = "debug"
    if arg in ("reset", "default"):
        ctx.data.pop(CTX_TG_DETAIL_LEVEL_SESSION, None)
        eff = detail_status.effective_detail_level(bot_cfg, ctx.data)
        return f"Detail level: {detail_status.detail_level_display(eff)}."
    if arg in ("off", "info", "debug"):
        ctx.data[CTX_TG_DETAIL_LEVEL_SESSION] = arg
        return f"Detail level: {detail_status.detail_level_display(arg)}."
    return "Usage: /detail off|info|verbose or /detail reset — alias: debug"


def _project_names_ordered() -> list[str]:
    return [p["name"] for p in projects.get_active_projects_list()]


def _project_inline_keyboard(names: list[str]) -> list[list[dict]]:
    p = TG_UI_CALLBACK_PREFIX
    rows: list[list[dict]] = []
    row: list[dict] = []
    for i, name in enumerate(names):
        row.append(
            {
                "text": _model_preset_button_label(name),
                "callback_data": f"{p}p|{i}",
            }
        )
        if len(row) >= 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return rows


def _model_preset_inline_keyboard(preset_names: list[str]) -> list[list[dict]]:
    p = TG_UI_CALLBACK_PREFIX
    rows: list[list[dict]] = []
    row: list[dict] = []
    for i, pname in enumerate(preset_names):
        row.append(
            {
                "text": _model_preset_button_label(pname),
                "callback_data": f"{p}m|{i}",
            }
        )
        if len(row) >= 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return rows


def _also_text_inline_keyboard() -> list[list[dict]]:
    p = TG_UI_CALLBACK_PREFIX
    return [
        [
            {"text": "On", "callback_data": f"{p}a|on"},
            {"text": "Off", "callback_data": f"{p}a|off"},
            {"text": "Reset", "callback_data": f"{p}a|reset"},
        ],
    ]


def _apply_also_text_setting(ctx: AgentContext, bot_cfg: dict, arg: str) -> str:
    """Apply on|off|reset for also_send_text session override. Returns user-facing reply."""
    arg = arg.strip().lower()
    if arg in ("reset", "default"):
        ctx.data.pop(CTX_TG_ALSO_SEND_TEXT_OVERRIDE, None)
        eff = speech.effective_also_send_text(bot_cfg, ctx.data)
        return f"Also send text: {'on' if eff else 'off'}."
    if arg in ("on", "enable", "yes"):
        ctx.data[CTX_TG_ALSO_SEND_TEXT_OVERRIDE] = "on"
        return "Also send text: on."
    if arg in ("off", "disable", "no"):
        ctx.data[CTX_TG_ALSO_SEND_TEXT_OVERRIDE] = "off"
        return "Also send text: off."
    return "Usage: /alsotext on|off|reset"


def _apply_output_optimize_mode(ctx: AgentContext, bot_cfg: dict, arg: str) -> str:
    """Apply auto/voice/text/off/reset; returns user-facing reply (mutates ctx.data)."""
    arg = arg.strip().lower()
    if arg in ("reset", "default"):
        ctx.data.pop(CTX_TG_OUTPUT_OPTIMIZE, None)
        eff = speech.effective_output_optimize_mode(bot_cfg, ctx.data)
        return f"Output optimize: {eff}."
    if arg == "off":
        ctx.data[CTX_TG_OUTPUT_OPTIMIZE] = "off"
        return "Output optimize: off (no extra style snippet)."
    if arg == "auto":
        ctx.data[CTX_TG_OUTPUT_OPTIMIZE] = "auto"
        return "Output optimize: auto (follows voice mode per turn)."
    if arg == "voice":
        ctx.data[CTX_TG_OUTPUT_OPTIMIZE] = "voice"
        return "Output optimize: voice (TTS-friendly)."
    if arg == "text":
        ctx.data[CTX_TG_OUTPUT_OPTIMIZE] = "text"
        return "Output optimize: text (Telegram reading)."
    return "Usage: /optimize_output auto|voice|text|off|reset — or /speakstyle (/speakstyle off)"


def _telegram_command_base(message: TgMessage) -> str:
    t = (message.text or "").strip()
    if not t:
        return ""
    return t.split(maxsplit=1)[0].split("@", 1)[0].lower()


def _mapped_context_id(bot_name: str, user_id: int, chat_id: int) -> str | None:
    key = _map_key(bot_name, user_id, chat_id)
    with _chat_map_lock:
        state = _load_state()
        return state.get("chats", {}).get(key)


def _persisted_chat_file_path(ctx_id: str) -> str:
    return files.get_abs_path(PERSISTED_CHATS_FOLDER, ctx_id, PERSISTED_CHAT_FILE_NAME)


def _parse_session_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    raw = str(value or "").strip()
    if not raw:
        return datetime.min
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return datetime.min


def _format_session_timestamp(value: object, *, with_date: bool = True) -> str:
    dt = _parse_session_datetime(value)
    if dt == datetime.min:
        return "unknown"
    return dt.strftime("%Y-%m-%d %H:%M" if with_date else "%H:%M")


def _format_session_date(value: object) -> str:
    dt = _parse_session_datetime(value)
    if dt == datetime.min:
        return "unknown"
    return dt.strftime("%Y-%m-%d")


def _session_browser_state_key(bot_name: str, user_id: int, chat_id: int) -> str:
    return _map_key(bot_name, user_id, chat_id)


def _load_session_browser_state(bot_name: str, user_id: int, chat_id: int) -> dict:
    key = _session_browser_state_key(bot_name, user_id, chat_id)
    with _chat_map_lock:
        state = _load_state()
        browsers = state.get("session_browser", {})
        data = browsers.get(key, {}) if isinstance(browsers, dict) else {}
    if not isinstance(data, dict):
        return {"query": "", "page": 0, "message_id": None}
    message_id = data.get("message_id")
    try:
        message_id = int(message_id) if message_id is not None else None
    except Exception:
        message_id = None
    return {
        "query": str(data.get("query") or "").strip(),
        "page": max(int(data.get("page") or 0), 0),
        "message_id": message_id,
    }


def _save_session_browser_state(
    bot_name: str,
    user_id: int,
    chat_id: int,
    *,
    query: str,
    page: int,
    message_id: int | None = None,
):
    key = _session_browser_state_key(bot_name, user_id, chat_id)
    with _chat_map_lock:
        state = _load_state()
        browsers = state.setdefault("session_browser", {})
        if not isinstance(browsers, dict):
            browsers = {}
            state["session_browser"] = browsers
        current = browsers.get(key, {}) if isinstance(browsers.get(key), dict) else {}
        current.update(
            {
                "query": str(query or "").strip(),
                "page": max(int(page or 0), 0),
                "message_id": int(message_id) if message_id is not None else current.get("message_id"),
                "updated_at": int(time.time()),
            }
        )
        browsers[key] = current
        _save_state(state)


def _normalize_session_line(text: str) -> str:
    line = re.sub(r"\s+", " ", str(text or "")).strip(" -–—	\n\r")
    if line.startswith("[Telegram message from") and line.endswith("]"):
        return ""
    lower = line.lower()
    if lower in {"body", "sender"} or lower.startswith("sender:"):
        return ""
    return line


def _extract_user_prompt_summary(meta: dict) -> str:
    log = meta.get("log") or {}
    logs = log.get("logs") if isinstance(log, dict) else []
    if not isinstance(logs, list):
        return ""
    for item in logs:
        if not isinstance(item, dict) or str(item.get("type") or "") != "user":
            continue
        content = str(item.get("content") or "")
        lines = [_normalize_session_line(line) for line in content.splitlines()]
        cleaned = [line for line in lines if line]
        if cleaned:
            return cleaned[0]
    return ""


def _trim_session_title(text: str, limit: int = 42) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if not value:
        return ""
    if len(value) <= limit:
        return value
    short = value[:limit].rstrip()
    if " " in short:
        short = short.rsplit(" ", 1)[0]
    return short.rstrip(" -–—:;,.!") + "…"


def _session_display_name(meta: dict) -> str:
    explicit = _trim_session_title(meta.get("name") or "")
    if explicit and not explicit.lower().startswith("telegram: @"):
        return explicit
    derived = _trim_session_title(_extract_user_prompt_summary(meta))
    if derived:
        return derived
    if explicit:
        return explicit
    data = meta.get("data") or {}
    username = str(data.get(CTX_TG_USERNAME) or "").strip()
    return f"Telegram chat @{username}" if username else "Untitled session"


def _session_message_count(meta: dict) -> int:
    log = meta.get("log") or {}
    logs = log.get("logs") if isinstance(log, dict) else []
    return len(logs) if isinstance(logs, list) else 0


def _read_persisted_chat_meta(ctx_id: str) -> dict | None:
    path = _persisted_chat_file_path(ctx_id)
    if not os.path.isfile(path):
        return None
    try:
        data = json.loads(files.read_file(path))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    meta = {
        "id": str(data.get("id") or ctx_id),
        "name": str(data.get("name") or "").strip(),
        "created_at": data.get("created_at") or "",
        "last_message": data.get("last_message") or data.get("created_at") or "",
        "data": data.get("data") or {},
        "log": data.get("log") or {},
    }
    if not isinstance(meta["data"], dict):
        meta["data"] = {}
    if not isinstance(meta["log"], dict):
        meta["log"] = {}
    meta["display_name"] = _session_display_name(meta)
    meta["message_count"] = _session_message_count(meta)
    return meta


def _session_matches_identity(meta: dict, bot_name: str, user_id: int, chat_id: int) -> bool:
    data = meta.get("data") or {}
    if not isinstance(data, dict):
        return False
    if str(data.get(CTX_TG_BOT) or "") != str(bot_name):
        return False
    try:
        if int(data.get(CTX_TG_USER_ID)) != int(user_id):
            return False
        if int(data.get(CTX_TG_CHAT_ID)) != int(chat_id):
            return False
    except Exception:
        return False
    return True


def _session_binding_state(meta: dict, bot_name: str, user_id: int, chat_id: int) -> str | None:
    data = meta.get("data") or {}
    if not isinstance(data, dict):
        return None

    tg_keys = (CTX_TG_BOT, CTX_TG_USER_ID, CTX_TG_CHAT_ID)
    has_any_tg_identity = any(str(data.get(key) or "").strip() for key in tg_keys)
    if not has_any_tg_identity:
        return "unbound"

    if _session_matches_identity(meta, bot_name, user_id, chat_id):
        return "bound"

    return None


def _list_switchable_sessions(
    bot_name: str, user_id: int, chat_id: int, limit: int | None = None
) -> list[dict]:
    chats_root = files.get_abs_path(PERSISTED_CHATS_FOLDER)
    if not os.path.isdir(chats_root):
        return []

    sessions: list[dict] = []
    for entry in os.listdir(chats_root):
        path = os.path.join(chats_root, entry)
        if not os.path.isdir(path):
            continue
        meta = _read_persisted_chat_meta(entry)
        if not meta:
            continue
        binding_state = _session_binding_state(meta, bot_name, user_id, chat_id)
        if not binding_state:
            continue
        meta["telegram_binding"] = binding_state
        sessions.append(meta)

    sessions.sort(
        key=lambda item: (
            _parse_session_datetime(item.get("last_message") or item.get("created_at")),
            str(item.get("id") or ""),
        ),
        reverse=True,
    )
    return sessions[:limit] if limit else sessions


def _filter_sessions_by_query(sessions: list[dict], query: str) -> list[dict]:
    q = str(query or "").strip().lower()
    if not q:
        return sessions
    result: list[dict] = []
    for meta in sessions:
        haystacks = [
            str(meta.get("display_name") or ""),
            str(meta.get("name") or ""),
            str(meta.get("id") or ""),
            _extract_user_prompt_summary(meta),
        ]
        if any(q in h.lower() for h in haystacks if h):
            result.append(meta)
    return result


def _session_page_slice(sessions: list[dict], page: int, page_size: int = 5) -> tuple[list[dict], int, int]:
    if page_size <= 0:
        page_size = 5
    total_pages = max((len(sessions) + page_size - 1) // page_size, 1)
    current_page = min(max(page, 0), total_pages - 1)
    start = current_page * page_size
    end = start + page_size
    return sessions[start:end], current_page, total_pages


def _session_list_header(active_label: str | None, total_count: int, query: str) -> str:
    lines = ["📂 Session picker", ""]
    if active_label:
        lines.append(f"Current: 🟢 {active_label}")
    else:
        lines.append("Current: none")
    if query:
        lines.append(f"Search: {query}")
    else:
        lines.append(f"Saved sessions: {total_count}")
    lines.append("")
    lines.append("Choose a session:")
    return "\n".join(lines)


def _session_selector_keyboard(
    sessions: list[dict],
    *,
    active_ctx_id: str | None,
    page: int,
    total_pages: int,
    has_query: bool,
) -> list[list[dict]]:
    p = TG_UI_CALLBACK_PREFIX
    rows: list[list[dict]] = []
    for meta in sessions:
        ctx_id = str(meta.get("id") or "").strip()
        if not ctx_id:
            continue
        binding_state = str(meta.get("telegram_binding") or "bound")
        if ctx_id == str(active_ctx_id or ""):
            marker = "🟢 "
        elif binding_state == "unbound":
            marker = "🌐 "
        else:
            marker = "💬 "
        rows.append([
            {
                "text": _model_preset_button_label(f"{marker}{meta.get('display_name') or ctx_id}"),
                "callback_data": f"{p}sv|{ctx_id}",
            }
        ])

    nav_row = [
        {"text": "◀️" if page > 0 else "·", "callback_data": f"{p}sp|prev"},
        {"text": f"{page + 1}/{total_pages}", "callback_data": f"{p}sp|stay"},
        {"text": "▶️" if page + 1 < total_pages else "·", "callback_data": f"{p}sp|next"},
    ]
    rows.append(nav_row)
    rows.append([
        {"text": "➕ New session", "callback_data": f"{p}sn|new"},
        {"text": "🔍 Search", "callback_data": f"{p}sh|help"},
    ])
    if has_query:
        rows.append([{"text": "✖️ Clear search", "callback_data": f"{p}sc|clear"}])
    return rows


def _session_details_text(meta: dict, active_ctx_id: str | None) -> str:
    ctx_id = str(meta.get("id") or "")
    active = ctx_id == str(active_ctx_id or "")
    binding_state = str(meta.get("telegram_binding") or "bound")
    if active:
        status = "🟢 active"
    elif binding_state == "unbound":
        status = "🔓 unbound web session"
    else:
        status = "⚪ inactive"
    lines = [
        f"📂 {meta.get('display_name') or ctx_id}",
        "",
        f"Status: {status}",
        f"Session ID: {ctx_id}",
        f"Created: {_format_session_date(meta.get('created_at'))}",
        f"Last activity: {_format_session_timestamp(meta.get('last_message'))}",
        f"Messages: {meta.get('message_count', 0)}",
    ]
    if binding_state == "unbound" and not active:
        lines.extend(["", "Opening this session will bind it to this Telegram chat."])
    summary = _extract_user_prompt_summary(meta)
    if summary:
        lines.extend(["", f"Topic: {_trim_session_title(summary, limit=80)}"])
    return "\n".join(lines)


def _session_details_keyboard(meta: dict, active_ctx_id: str | None) -> list[list[dict]]:
    p = TG_UI_CALLBACK_PREFIX
    ctx_id = str(meta.get("id") or "")
    is_active = ctx_id == str(active_ctx_id or "")
    binding_state = str(meta.get("telegram_binding") or "bound")
    if is_active:
        switch_label = "🟢 Already active"
    elif binding_state == "unbound":
        switch_label = "✅ Open and bind to this chat"
    else:
        switch_label = "✅ Open this session"
    return [
        [{"text": switch_label, "callback_data": f"{p}ss|{ctx_id}"}],
        [{"text": "⬅️ Back", "callback_data": f"{p}sb|back"}],
    ]


def _session_search_help_text() -> str:
    return (
        "🔍 Search sessions\n\n"
        "Use /session search <term> to filter old chats by title, topic, or session ID.\n"
        "Example: /session search prtg"
    )


def _resolve_session_target(sessions: list[dict], arg: str) -> dict | None:
    value = (arg or "").strip()
    if not value:
        return None
    if value.isdigit():
        idx = int(value) - 1
        if 0 <= idx < len(sessions):
            return sessions[idx]
        return None
    exact = [s for s in sessions if str(s.get("id") or "") == value]
    if exact:
        return exact[0]
    prefix = [s for s in sessions if str(s.get("id") or "").startswith(value)]
    if len(prefix) == 1:
        return prefix[0]
    title_matches = [
        s
        for s in sessions
        if str(s.get("display_name") or "").strip().lower() == value.lower()
    ]
    if len(title_matches) == 1:
        return title_matches[0]
    return None


def _session_render_payload(
    bot_name: str,
    user_id: int,
    chat_id: int,
    *,
    active_ctx_id: str | None,
    query: str,
    page: int,
) -> tuple[str, list[list[dict]] | None, int]:
    sessions = _list_switchable_sessions(bot_name, user_id, chat_id)
    active_meta = next((s for s in sessions if str(s.get("id") or "") == str(active_ctx_id or "")), None)
    active_label = str(active_meta.get("display_name") or "").strip() if active_meta else ""
    if not active_label and active_ctx_id:
        live_ctx = AgentContext.get(active_ctx_id)
        active_label = _trim_session_title(getattr(live_ctx, "name", "") or active_ctx_id, limit=48)
    filtered = _filter_sessions_by_query(sessions, query)

    if not filtered:
        if query:
            text = (
                "📂 Session picker\n\n"
                f"Search: {query}\n\n"
                "No matching saved sessions found.\n"
                "Use /session search <term> or clear the search."
            )
            keyboard = [[{"text": "✖️ Clear search", "callback_data": f"{TG_UI_CALLBACK_PREFIX}sc|clear"}]]
            return text, keyboard, 0
        text = (
            "📂 Session picker\n\n"
            "No saved sessions for this Telegram chat yet.\n"
            "Send a message or start a new session."
        )
        keyboard = [[{"text": "➕ New session", "callback_data": f"{TG_UI_CALLBACK_PREFIX}sn|new"}]]
        return text, keyboard, 0

    page_sessions, current_page, total_pages = _session_page_slice(filtered, page)
    text = _session_list_header(active_label or None, len(filtered), query)
    keyboard = _session_selector_keyboard(
        page_sessions,
        active_ctx_id=active_ctx_id,
        page=current_page,
        total_pages=total_pages,
        has_query=bool(query),
    )
    return text, keyboard, current_page


def _load_persisted_context(
    ctx_id: str,
    bot_cfg: dict,
    *,
    expected_bot_name: str | None = None,
    expected_user_id: int | None = None,
    expected_chat_id: int | None = None,
) -> AgentContext | None:
    meta = _read_persisted_chat_meta(ctx_id)
    if not meta:
        return None

    if (
        expected_bot_name is not None
        and expected_user_id is not None
        and expected_chat_id is not None
        and not _session_matches_identity(meta, expected_bot_name, expected_user_id, expected_chat_id)
    ):
        PrintStyle.warning(
            f"Telegram: refusing to load persisted chat {ctx_id} for mismatched identity"
        )
        return None

    existing = AgentContext.get(ctx_id)
    if existing:
        existing.data[CTX_TG_BOT_CFG] = bot_cfg
        return existing

    path = _persisted_chat_file_path(ctx_id)
    try:
        payload = json.loads(files.read_file(path))
        ctx = _deserialize_context(payload)
        ctx.data[CTX_TG_BOT_CFG] = bot_cfg
        return ctx
    except Exception as e:
        PrintStyle.warning(f"Telegram: failed to load persisted chat {ctx_id}: {format_error(e)}")
        return None


def _activate_existing_session(
    bot_name: str,
    bot_cfg: dict,
    user_id: int,
    chat_id: int,
    target_ctx_id: str,
) -> tuple[bool, str, AgentContext | None]:
    sessions = _list_switchable_sessions(bot_name, user_id, chat_id)
    target = next((s for s in sessions if str(s.get("id") or "") == str(target_ctx_id)), None)
    if not target:
        return False, "Session not found for this Telegram chat.", None

    binding_state = str(target.get("telegram_binding") or "bound")
    if binding_state == "unbound":
        ctx = _load_persisted_context(target_ctx_id, bot_cfg)
    else:
        ctx = _load_persisted_context(
            target_ctx_id,
            bot_cfg,
            expected_bot_name=bot_name,
            expected_user_id=user_id,
            expected_chat_id=chat_id,
        )
    if not ctx:
        return False, "Failed to load that saved session.", None

    if binding_state == "unbound":
        ctx.data[CTX_TG_BOT] = bot_name
        ctx.data[CTX_TG_USER_ID] = user_id
        ctx.data[CTX_TG_CHAT_ID] = chat_id

    key = _map_key(bot_name, user_id, chat_id)
    with _chat_map_lock:
        state = _load_state()
        chats = state.setdefault("chats", {})
        old_ctx_id = chats.get(key)
        if old_ctx_id and old_ctx_id != ctx.id:
            old_ctx = AgentContext.get(old_ctx_id)
            if old_ctx:
                old_ctx.kill_process()
                save_tmp_chat(old_ctx)
        chats[key] = ctx.id
        _save_state(state)

    save_tmp_chat(ctx)
    suffix = " Bound to this Telegram chat." if binding_state == "unbound" else ""
    return (
        True,
        f"Switched to {target.get('display_name') or ctx.id}. Last activity: {_format_session_timestamp(target.get('last_message'))}.{suffix}",
        ctx,
    )


async def _start_new_session_for_user(
    bot_name: str,
    bot_cfg: dict,
    user_id: int,
    username: str | None,
    chat_id: int,
) -> tuple[bool, str, AgentContext | None]:
    key = _map_key(bot_name, user_id, chat_id)

    with _chat_map_lock:
        state = _load_state()
        chats = state.setdefault("chats", {})
        old_ctx_id = chats.pop(key, None)
        if old_ctx_id:
            old_ctx = AgentContext.get(old_ctx_id)
            if old_ctx:
                old_ctx.kill_process()
                save_tmp_chat(old_ctx)
            _save_state(state)

    ctx = await _get_or_create_context_from_user(bot_name, bot_cfg, user_id, username, chat_id)
    if not ctx:
        return False, "Failed to create a new session.", None
    return True, "New chat started. Previous conversation is still available in the session list.", ctx


async def _show_session_picker(
    token: str,
    chat_id: int,
    *,
    bot_name: str,
    user_id: int,
    active_ctx_id: str | None,
    query: str,
    page: int,
    message_id: int | None = None,
) -> int | None:
    text, keyboard, current_page = _session_render_payload(
        bot_name,
        user_id,
        chat_id,
        active_ctx_id=active_ctx_id,
        query=query,
        page=page,
    )
    async with _temp_bot(token) as bot:
        if message_id:
            edited = await tc.edit_text_with_keyboard(
                bot, chat_id, message_id, text, keyboard or [], parse_mode=None
            )
            if edited:
                _save_session_browser_state(
                    bot_name, user_id, chat_id, query=query, page=current_page, message_id=message_id
                )
                return message_id
        sent_id = await tc.send_text_with_keyboard(
            bot, chat_id, text, keyboard or [], parse_mode=None
        )
    if sent_id is not None:
        _save_session_browser_state(
            bot_name, user_id, chat_id, query=query, page=current_page, message_id=sent_id
        )
    return sent_id


async def _show_session_details(
    token: str,
    chat_id: int,
    *,
    active_ctx_id: str | None,
    meta: dict,
    message_id: int | None = None,
) -> int | None:
    text = _session_details_text(meta, active_ctx_id)
    keyboard = _session_details_keyboard(meta, active_ctx_id)
    async with _temp_bot(token) as bot:
        if message_id:
            edited = await tc.edit_text_with_keyboard(
                bot, chat_id, message_id, text, keyboard, parse_mode=None
            )
            if edited:
                return message_id
        return await tc.send_text_with_keyboard(bot, chat_id, text, keyboard, parse_mode=None)


def _get_existing_context(message: TgMessage, bot_name: str) -> AgentContext | None:
    user = message.from_user
    if not user:
        return None
    ctx_id = _mapped_context_id(bot_name, user.id, message.chat.id)
    if not ctx_id:
        return None
    ctx = AgentContext.get(ctx_id)
    if ctx:
        return ctx
    ctx = _load_persisted_context(
        ctx_id,
        {},
        expected_bot_name=bot_name,
        expected_user_id=user.id,
        expected_chat_id=message.chat.id,
    )
    if ctx:
        return ctx
    key = _map_key(bot_name, user.id, message.chat.id)
    with _chat_map_lock:
        state = _load_state()
        chats = state.get("chats", {})
        if chats.get(key) == ctx_id:
            chats.pop(key, None)
            _save_state(state)
    return None


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
                ctx.data.pop(CTX_TG_OUTPUT_OPTIMIZE, None)
                ctx.data.pop(CTX_TG_VOICE_TEXT, None)
                ctx.data.pop(CTX_TG_DETAIL_LEVEL_SESSION, None)
                ctx.data.pop(CTX_TG_DETAIL_LAST_SENT_TS, None)
                ctx.data.pop(CTX_TG_PROGRESS_MESSAGE_ID, None)
                ctx.data.pop(CTX_TG_PROGRESS_LAST_HASH, None)
                ctx.data.pop(CTX_TG_PROGRESS_LAST_TS, None)
                save_tmp_chat(ctx)
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


async def handle_newchat(message: TgMessage, bot_name: str, bot_cfg: dict):
    """Handle /newchat — start a fresh AgentContext; the old chat stays in the browser UI."""
    user = message.from_user
    if not user or not _is_allowed(bot_cfg, user.id, user.username):
        return
    instance = get_bot(bot_name)
    if not instance:
        return

    _, reply, _ = await _start_new_session_for_user(
        bot_name, bot_cfg, user.id, user.username, message.chat.id
    )
    await _send_with_temp_bot(
        instance.bot.token, message.chat.id, reply, parse_mode=None
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


async def handle_voice(message: TgMessage, bot_name: str, bot_cfg: dict):
    """Handle /voice — walkie-talkie conversation mode for the current session."""
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
        reply = (
            f"{_voice_mode_header(ctx)}\n"
            "Choose a mode: voice only, voice + text, text only, or off.\n"
            "Tip: send a voice message and the session stays in the selected reply style."
        )
        kb = _voice_mode_inline_keyboard()
        save_tmp_chat(ctx)
        await _send_with_temp_bot(
            instance.bot.token, message.chat.id, reply, parse_mode=None, keyboard=kb
        )
        return

    if arg in ("start", "on", "enable", "voice_only", "voice_text", "text_only", "off"):
        reply = _apply_voice_mode_setting(ctx, arg)
    else:
        reply = "Usage: /voice [voice_only|voice_text|text_only|off]"

    save_tmp_chat(ctx)
    await _send_with_temp_bot(instance.bot.token, message.chat.id, reply, parse_mode=None)


async def handle_tts(message: TgMessage, bot_name: str, bot_cfg: dict):
    """Handle /tts — per-session voice reply mode."""
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
        desc = _tts_session_description(ctx, bot_cfg)
        reply = (
            f"Voice replies: {desc}.\n"
            "Tap a button or type /tts on|off|auto|force"
        )
        kb = _tts_inline_keyboard()
        save_tmp_chat(ctx)
        await _send_with_temp_bot(
            instance.bot.token, message.chat.id, reply, parse_mode=None, keyboard=kb
        )
        return

    if arg in ("on", "enable"):
        reply = _apply_tts_setting(ctx, "on", bot_cfg)
    elif arg in ("off", "disable"):
        reply = _apply_tts_setting(ctx, "off", bot_cfg)
    elif arg == "auto":
        reply = _apply_tts_setting(ctx, "auto", bot_cfg)
    elif arg == "force":
        reply = _apply_tts_setting(ctx, "force", bot_cfg)
    else:
        reply = "Usage: /tts on|off|auto|force"

    save_tmp_chat(ctx)
    await _send_with_temp_bot(instance.bot.token, message.chat.id, reply, parse_mode=None)


async def handle_detail(message: TgMessage, bot_name: str, bot_cfg: dict):
    """Handle /detail — per-session tool status verbosity: off | info | verbose (internal: debug)."""
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
        desc = _detail_session_description(ctx, bot_cfg)
        reply = (
            f"Tool detail: {desc}.\n"
            "Tap a button or type /detail off|info|verbose or /detail reset"
        )
        kb = _detail_inline_keyboard()
        save_tmp_chat(ctx)
        await _send_with_temp_bot(
            instance.bot.token, message.chat.id, reply, parse_mode=None, keyboard=kb
        )
        return

    reply = _apply_detail_level(ctx, bot_cfg, arg)
    save_tmp_chat(ctx)
    await _send_with_temp_bot(instance.bot.token, message.chat.id, reply, parse_mode=None)


async def handle_optimize_output(message: TgMessage, bot_name: str, bot_cfg: dict):
    """Handle /optimize_output and /speakstyle — session prompt style for voice vs text."""
    user = message.from_user
    if not user or not _is_allowed(bot_cfg, user.id, user.username):
        return
    ctx = await _get_or_create_context(bot_name, bot_cfg, message)
    if not ctx:
        return
    instance = get_bot(bot_name)
    if not instance:
        return

    base = _telegram_command_base(message)
    raw = (message.text or "").strip()
    parts = raw.split(maxsplit=1)
    arg = parts[1].strip().lower() if len(parts) > 1 else ""

    if base == "/speakstyle":
        if not arg:
            arg = "voice"
        elif arg in ("off", "disable"):
            arg = "off"
        elif arg in ("on", "voice", "enable"):
            arg = "voice"

    if base == "/optimize_output" and not arg:
        eff = speech.effective_output_optimize_mode(bot_cfg, ctx.data)
        reply = (
            f"Output optimize: {eff}.\n"
            "Tap a button or type: auto | voice | text | off | reset\n"
            "/speakstyle — shortcut for voice; /speakstyle off"
        )
        kb = _optimize_output_inline_keyboard()
        save_tmp_chat(ctx)
        await _send_with_temp_bot(
            instance.bot.token, message.chat.id, reply, parse_mode=None, keyboard=kb
        )
        return

    if arg in ("reset", "default", "off", "auto", "voice", "text"):
        reply = _apply_output_optimize_mode(ctx, bot_cfg, arg)
    else:
        reply = "Usage: /optimize_output auto|voice|text|off|reset — or /speakstyle (/speakstyle off)"

    save_tmp_chat(ctx)
    await _send_with_temp_bot(instance.bot.token, message.chat.id, reply, parse_mode=None)


async def handle_also_text(message: TgMessage, bot_name: str, bot_cfg: dict):
    """Handle /alsotext — toggle also_send_text per session."""
    user = message.from_user
    if not user or not _is_allowed(bot_cfg, user.id, user.username):
        return
    ctx = await _get_or_create_context(bot_name, bot_cfg, message)
    if not ctx:
        return
    instance = get_bot(bot_name)
    if not instance:
        return

    arg = _cmd_rest(message).lower()

    if not arg:
        eff = speech.effective_also_send_text(bot_cfg, ctx.data)
        reply = (
            f"Also send text: {'on' if eff else 'off'}.\n"
            "Tap a button or type: on | off | reset"
        )
        kb = _also_text_inline_keyboard()
        save_tmp_chat(ctx)
        await _send_with_temp_bot(
            instance.bot.token, message.chat.id, reply, parse_mode=None, keyboard=kb
        )
        return

    if arg in ("reset", "default", "on", "enable", "yes", "off", "disable", "no"):
        reply = _apply_also_text_setting(ctx, bot_cfg, arg)
    else:
        reply = "Usage: /alsotext on|off|reset"

    save_tmp_chat(ctx)
    await _send_with_temp_bot(instance.bot.token, message.chat.id, reply, parse_mode=None)


def _status_on_off(enabled: bool) -> str:
    return "on" if enabled else "off"


def _status_humanize_model_field(raw: object) -> str:
    s = str(raw or "").strip()
    low = s.lower()
    if low in ("?", ""):
        return "unknown"
    if low == "other":
        return "other (custom)"
    return s


def _status_model_code(provider: str, name: str, esc) -> str:
    p = esc(_status_humanize_model_field(provider))
    n = esc(_status_humanize_model_field(name))
    return f"<code>{p}</code>/<code>{n}</code>"


async def handle_status(message: TgMessage, bot_name: str, bot_cfg: dict):
    """Handle /status — model, tokens, project, TTS/STT, run state."""
    user = message.from_user
    if not user or not _is_allowed(bot_cfg, user.id, user.username):
        return
    instance = get_bot(bot_name)
    if not instance:
        return

    ctx = _get_existing_context(message, bot_name)

    def esc(s: object) -> str:
        return html.escape(str(s))

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

    header = f"🤖 <b>Agent status</b>\n<code>{esc(bot_name)}</code>"
    lines: list[str] = []

    chat_m = _status_model_code(chat_provider, chat_name, esc)
    util_m = _status_model_code(util_provider, util_name, esc)
    lines.append(f"🧠 <b>Chat</b>: {chat_m}")
    lines.append(f"🔧 <b>Utility</b>: {util_m}")

    if ctx:
        agent = ctx.agent0
        hist_tokens = agent.history.get_tokens()
        ctx_window = agent.get_data(Agent.DATA_NAME_CTX_WINDOW) or {}
        win_tokens = int((ctx_window.get("tokens") or 0))
        pct = (100.0 * hist_tokens / hist_limit) if hist_limit else 0.0
        hist_pct = f"{pct:.1f}%" if hist_limit else "n/a"
        lines.insert(
            0,
            f"⚡ <b>Activity</b>: {'running' if ctx.is_running() else 'idle'} · paused "
            f"{'yes' if ctx.paused else 'no'}",
        )
        lines.append(
            f"📚 <b>Context</b>: ~{hist_tokens} / ~{hist_limit} tok ({hist_pct}) · "
            f"~{win_tokens} prompt (est.) · {agent.history.counter} msgs"
        )

        vm = speech.effective_voice_reply_mode(bot_cfg, ctx.data)
        talk_mode = _voice_conversation_mode(ctx)
        talk_disp = _voice_mode_label(talk_mode)
        tts_ic = "✅" if speech.tts_enabled(bot_cfg) else "❌"
        stt_ic = "✅" if speech.stt_enabled(bot_cfg) else "❌"
        voice_prefix = "🎙 active" if talk_mode != "off" else "🎙 off"
        lines.append(
            f"🔊 <b>Voice</b>: TTS {tts_ic} {_status_on_off(speech.tts_enabled(bot_cfg))} · "
            f"STT {stt_ic} {_status_on_off(speech.stt_enabled(bot_cfg))} · "
            f"replies <code>{esc(vm)}</code> · {voice_prefix} <code>{esc(talk_disp)}</code>"
        )

        opt_eff = speech.effective_output_optimize_mode(bot_cfg, ctx.data)
        also_eff = speech.effective_also_send_text(bot_cfg, ctx.data)
        det_eff = detail_status.effective_detail_level(bot_cfg, ctx.data)
        det_eff_disp = detail_status.detail_level_display(det_eff)
        lines.append(
            f"⚙️ <b>Reply</b>: shaping <code>{esc(opt_eff)}</code> · "
            f"also text <code>{'on' if also_eff else 'off'}</code> · "
            f"tool detail <code>{esc(det_eff_disp)}</code>"
        )

        proj = projects.get_context_project_name(ctx)
        proj_disp = f"<code>{esc(proj)}</code>" if proj else "<i>none</i>"
        lines.append(f"📁 <b>Project</b>: {proj_disp}")

        proj_hint = f" · <code>{esc(proj)}</code>" if proj else ""
        lines.append(f"🧵 <b>Session</b>: <code>{esc(ctx.id)}</code>{proj_hint}")
    else:
        lines.insert(
            0,
            "💤 <b>Session</b>: <i>no active session</i> — send a message or use /start",
        )
        tts_ic = "✅" if speech.tts_enabled(bot_cfg) else "❌"
        stt_ic = "✅" if speech.stt_enabled(bot_cfg) else "❌"
        vm = speech.effective_voice_reply_mode(bot_cfg, {})
        lines.append(
            f"🔊 <b>Voice</b>: TTS {tts_ic} {_status_on_off(speech.tts_enabled(bot_cfg))} · "
            f"STT {stt_ic} {_status_on_off(speech.stt_enabled(bot_cfg))} · "
            f"replies <code>{esc(vm)}</code> · 🎙 off <code>off</code>"
        )
        def_det = detail_status.normalize_detail_level(bot_cfg.get("telegram_detail_level"))
        def_det_disp = detail_status.detail_level_display(def_det)
        lines.append(
            f"⚙️ <b>Reply</b>: shaping <code>{esc(speech.optimize_output_default(bot_cfg))}</code> · "
            f"tool detail <code>{esc(def_det_disp)}</code>"
        )

    text = header + "\n\n" + "\n".join(lines)
    await _send_with_temp_bot(
        instance.bot.token, message.chat.id, text, parse_mode=ParseMode.HTML
    )


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
    names = _project_names_ordered()
    if not arg:
        active = projects.get_context_project_name(ctx)
        lines = [
            f"Active project: {active or '(none)'}",
            "Available: " + (", ".join(names) if names else "(none)"),
        ]
        kb = None
        if names:
            kb = _project_inline_keyboard(names)
            lines.append("Tap a button to switch, or type /project <name>")
        reply = "\n".join(lines)
        await _send_with_temp_bot(
            instance.bot.token, message.chat.id, reply, parse_mode=None, keyboard=kb
        )
        return

    name_set = set(names)
    if arg not in name_set:
        reply = f"Unknown project: {arg}. Use /project to list."
    else:
        try:
            projects.activate_project(ctx.id, arg)
            save_tmp_chat(ctx)
            reply = f"Switched project to: {arg}"
        except Exception as e:
            reply = f"Failed to switch project: {format_error(e)}"

    await _send_with_temp_bot(instance.bot.token, message.chat.id, reply, parse_mode=None)


async def handle_session(message: TgMessage, bot_name: str, bot_cfg: dict):
    user = message.from_user
    if not user or not _is_allowed(bot_cfg, user.id, user.username):
        return
    instance = get_bot(bot_name)
    if not instance:
        return

    active_ctx_id = _mapped_context_id(bot_name, user.id, message.chat.id)
    ctx = _get_existing_context(message, bot_name)
    if ctx:
        ctx.data[CTX_TG_BOT_CFG] = bot_cfg
        active_ctx_id = ctx.id

    arg = _cmd_rest(message).strip()
    if not arg:
        await _show_session_picker(
            instance.bot.token,
            message.chat.id,
            bot_name=bot_name,
            user_id=user.id,
            active_ctx_id=active_ctx_id,
            query="",
            page=0,
        )
        return

    parts = arg.split(maxsplit=1)
    if parts and parts[0].lower() == "search":
        query = parts[1].strip() if len(parts) > 1 else ""
        if not query:
            await _send_with_temp_bot(
                instance.bot.token, message.chat.id, _session_search_help_text(), parse_mode=None
            )
            return
        await _show_session_picker(
            instance.bot.token,
            message.chat.id,
            bot_name=bot_name,
            user_id=user.id,
            active_ctx_id=active_ctx_id,
            query=query,
            page=0,
        )
        return

    browser = _load_session_browser_state(bot_name, user.id, message.chat.id)
    all_sessions = _list_switchable_sessions(bot_name, user.id, message.chat.id)
    if arg.isdigit() and browser.get("query"):
        resolve_sessions = _filter_sessions_by_query(all_sessions, browser.get("query", ""))
    else:
        resolve_sessions = all_sessions
    target = _resolve_session_target(resolve_sessions, arg)
    if not target:
        reply = "Unknown session. Use /session or /session search <term>."
        await _send_with_temp_bot(instance.bot.token, message.chat.id, reply, parse_mode=None)
        return

    ok, reply, target_ctx = _activate_existing_session(
        bot_name, bot_cfg, user.id, message.chat.id, str(target.get("id") or "")
    )
    if ok and target_ctx:
        target_ctx.data[CTX_TG_BOT_CFG] = bot_cfg
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
        preset_names = [
            str(p.get("name", "")).strip()
            for p in mc.get_presets()
            if p.get("name")
        ]
        if preset_names:
            lines.append("Presets: " + ", ".join(preset_names))
        kb = None
        if mc.is_chat_override_allowed(ctx.agent0) and preset_names:
            kb = _model_preset_inline_keyboard(preset_names)
            lines.append("Tap a button to switch preset, or type /model <name>")
        reply = "\n".join(lines)
        await _send_with_temp_bot(
            instance.bot.token, message.chat.id, reply, parse_mode=None, keyboard=kb
        )
        return

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

    # New user turn: clear stale progress message state
    _clear_progress_state(context)

    # Show an immediate live-status placeholder so long agent runs don't look frozen.
    await _send_initial_progress_status(context)

    # Store stop event so send_telegram_reply can cancel typing
    context.data[CTX_TG_TYPING_STOP] = typing_stop
    context.data.pop(CTX_TG_DETAIL_LAST_SENT_TS, None)

    # Keep Telegram threading visible when the user replied to an earlier message.
    reply_to_id = message.message_id if message.reply_to_message else None
    context.data[CTX_TG_REPLY_TO] = reply_to_id

    # Build user message text
    text = _extract_message_content(message)
    reply_context = _extract_reply_context(message)
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

    if reply_context:
        context.data[CTX_TG_REPLY_CONTEXT] = reply_context
        text = _merge_reply_context(text, reply_context)
    else:
        context.data.pop(CTX_TG_REPLY_CONTEXT, None)

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

    raw_data = query.data or ""
    parsed = _parse_plugin_ui_callback(raw_data)

    if parsed:
        kind, payload = parsed
        instance = get_bot(bot_name)
        if not instance:
            await query.answer("Bot unavailable.")
            return
        token = instance.bot.token
        chat_id = query.message.chat.id

        if kind in {"s", "ss"}:
            ok, reply, target_ctx = _activate_existing_session(
                bot_name, bot_cfg, user.id, chat_id, payload
            )
            if ok and target_ctx:
                target_ctx.data[CTX_TG_BOT_CFG] = bot_cfg
                await query.answer("Switched")
                active_ctx_id = target_ctx.id
                if kind == "ss":
                    browser = _load_session_browser_state(bot_name, user.id, chat_id)
                    await _show_session_picker(
                        token,
                        chat_id,
                        bot_name=bot_name,
                        user_id=user.id,
                        active_ctx_id=active_ctx_id,
                        query=browser.get("query", ""),
                        page=browser.get("page", 0),
                        message_id=query.message.message_id,
                    )
                else:
                    await _send_with_temp_bot(token, chat_id, reply, parse_mode=None)
            else:
                await query.answer("Failed")
                await _send_with_temp_bot(token, chat_id, reply, parse_mode=None)
            return

        if kind == "sv":
            sessions = _list_switchable_sessions(bot_name, user.id, chat_id)
            target = next((s for s in sessions if str(s.get("id") or "") == payload), None)
            if not target:
                await query.answer("Session not found")
                return
            await _show_session_details(
                token,
                chat_id,
                active_ctx_id=_mapped_context_id(bot_name, user.id, chat_id),
                meta=target,
                message_id=query.message.message_id,
            )
            await query.answer()
            return

        if kind == "sp":
            browser = _load_session_browser_state(bot_name, user.id, chat_id)
            page = int(browser.get("page", 0) or 0)
            if payload == "next":
                page += 1
            elif payload == "prev":
                page = max(page - 1, 0)
            await _show_session_picker(
                token,
                chat_id,
                bot_name=bot_name,
                user_id=user.id,
                active_ctx_id=_mapped_context_id(bot_name, user.id, chat_id),
                query=browser.get("query", ""),
                page=page,
                message_id=query.message.message_id,
            )
            await query.answer()
            return

        if kind == "sb":
            browser = _load_session_browser_state(bot_name, user.id, chat_id)
            await _show_session_picker(
                token,
                chat_id,
                bot_name=bot_name,
                user_id=user.id,
                active_ctx_id=_mapped_context_id(bot_name, user.id, chat_id),
                query=browser.get("query", ""),
                page=browser.get("page", 0),
                message_id=query.message.message_id,
            )
            await query.answer()
            return

        if kind == "sh":
            async with _temp_bot(token) as bot:
                await tc.edit_text_with_keyboard(
                    bot,
                    chat_id,
                    query.message.message_id,
                    _session_search_help_text(),
                    [[{"text": "⬅️ Back", "callback_data": f"{TG_UI_CALLBACK_PREFIX}sb|back"}]],
                    parse_mode=None,
                )
            await query.answer()
            return

        if kind == "sc":
            await _show_session_picker(
                token,
                chat_id,
                bot_name=bot_name,
                user_id=user.id,
                active_ctx_id=_mapped_context_id(bot_name, user.id, chat_id),
                query="",
                page=0,
                message_id=query.message.message_id,
            )
            await query.answer()
            return

        if kind == "sn":
            ok, reply, new_ctx = await _start_new_session_for_user(
                bot_name, bot_cfg, user.id, user.username, chat_id
            )
            active_ctx_id = new_ctx.id if ok and new_ctx else _mapped_context_id(bot_name, user.id, chat_id)
            await _show_session_picker(
                token,
                chat_id,
                bot_name=bot_name,
                user_id=user.id,
                active_ctx_id=active_ctx_id,
                query="",
                page=0,
                message_id=query.message.message_id,
            )
            await query.answer("Started" if ok else "Failed")
            await _send_with_temp_bot(token, chat_id, reply, parse_mode=None)
            return

        context = await _get_or_create_context_from_user(
            bot_name, bot_cfg, user.id, user.username, chat_id,
        )
        if not context:
            await query.answer("No session. Use /start first.")
            return

        if kind == "o":
            if payload not in ("auto", "voice", "text", "off", "reset"):
                await query.answer("Unknown option.")
                return
            reply = _apply_output_optimize_mode(context, bot_cfg, payload)
            save_tmp_chat(context)
            await query.answer("Updated")
            await _send_with_temp_bot(token, chat_id, reply, parse_mode=None)
            return

        if kind == "a":
            if payload not in ("on", "off", "reset"):
                await query.answer("Unknown option.")
                return
            reply = _apply_also_text_setting(context, bot_cfg, payload)
            save_tmp_chat(context)
            await query.answer("OK")
            await _send_with_temp_bot(token, chat_id, reply, parse_mode=None)
            return

        if kind == "v":
            if payload not in ("voice_only", "voice_text", "text_only", "off"):
                await query.answer("Unknown option.")
                return
            reply = _apply_voice_mode_setting(context, payload)
            save_tmp_chat(context)
            await query.answer("OK")
            await _send_with_temp_bot(token, chat_id, reply, parse_mode=None)
            return

        if kind == "qa":
            action, _, action_token = payload.partition(":")
            if action != "show_text":
                await query.answer("Unknown option.")
                return
            text_reply = str(context.data.get(CTX_TG_LAST_TEXT_RESPONSE, "") or "").strip()
            current_token = str(context.data.get(CTX_TG_LAST_TEXT_RESPONSE_TOKEN, "") or "")
            if not text_reply or not current_token or current_token != action_token:
                await query.answer("Text is no longer available.")
                return
            async with _temp_bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML)) as bot:
                await tc.send_text(
                    bot,
                    chat_id,
                    tc.md_to_telegram_html(text_reply),
                    reply_to_message_id=(query.message.message_id if query.message else None),
                )
            await query.answer("Shown")
            return

        if kind == "m":
            try:
                from plugins._model_config.helpers import model_config as mc
            except Exception:
                await query.answer("Model plugin missing.")
                return
            if not mc.is_chat_override_allowed(context.agent0):
                await query.answer("Override disabled.")
                return
            try:
                idx = int(payload)
            except ValueError:
                await query.answer("Invalid preset.")
                return
            preset_names = [
                str(p.get("name", "")).strip()
                for p in mc.get_presets()
                if p.get("name")
            ]
            if idx < 0 or idx >= len(preset_names):
                await query.answer("List changed — send /model again.")
                return
            pname = preset_names[idx]
            context.set_data("chat_model_override", {"preset_name": pname})
            save_tmp_chat(context)
            reply = f"Model preset set to: {pname}"
            await query.answer("OK")
            await _send_with_temp_bot(token, chat_id, reply, parse_mode=None)
            return

        if kind == "t":
            if payload not in ("on", "off", "auto", "force"):
                await query.answer("Unknown option.")
                return
            reply = _apply_tts_setting(context, payload, bot_cfg)
            save_tmp_chat(context)
            await query.answer("OK")
            await _send_with_temp_bot(token, chat_id, reply, parse_mode=None)
            return

        if kind == "d":
            if payload not in ("off", "info", "debug", "reset"):
                await query.answer("Unknown option.")
                return
            reply = _apply_detail_level(context, bot_cfg, payload)
            save_tmp_chat(context)
            await query.answer("OK")
            await _send_with_temp_bot(token, chat_id, reply, parse_mode=None)
            return

        if kind == "p":
            try:
                idx = int(payload)
            except ValueError:
                await query.answer("Invalid project.")
                return
            pnames = _project_names_ordered()
            if idx < 0 or idx >= len(pnames):
                await query.answer("List changed — send /project again.")
                return
            pname = pnames[idx]
            try:
                projects.activate_project(context.id, pname)
                save_tmp_chat(context)
                reply = f"Switched project to: {pname}"
            except Exception as e:
                reply = f"Failed to switch project: {format_error(e)}"
            await query.answer("OK")
            await _send_with_temp_bot(token, chat_id, reply, parse_mode=None)
            return

        await query.answer("Unknown action.")
        return

    await query.answer()

    # Treat callback data as a user message (agent / response-tool keyboards)
    text = raw_data
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

        # Check if existing context is still alive or can be restored from persisted chats
        if ctx_id:
            ctx = AgentContext.get(ctx_id) or _load_persisted_context(
                ctx_id,
                bot_cfg,
                expected_bot_name=bot_name,
                expected_user_id=user_id,
                expected_chat_id=chat_id,
            )
            if ctx:
                # Keep snapshot in sync with current plugin external config (handlers pass fresh bot_cfg).
                # Without this, TTS/STT/progress/system prompt keep using values from first session creation.
                ctx.data[CTX_TG_BOT_CFG] = bot_cfg
                return ctx
            # Context no longer exists on disk or in memory, remove stale mapping
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

            d_opt = speech.optimize_output_default(bot_cfg)
            if d_opt in ("voice", "text"):
                ctx.data[CTX_TG_OUTPUT_OPTIMIZE] = d_opt

            project = _get_project(bot_cfg, user_id)
            if project:
                projects.activate_project(ctx.id, project)

            # Inherit model override from an existing context in the same project
            _inherit_model_override(ctx)

            chats[key] = ctx.id
            _save_state(state)

            save_tmp_chat(ctx)

            PrintStyle.success(
                f"Telegram ({bot_name}): new chat {ctx.id} for user {display_name}"
            )
            return ctx

        except Exception as e:
            PrintStyle.error(f"Telegram: failed to create context: {format_error(e)}")
            return None

# Message content extraction

def _truncate_preview(text: str, limit: int = 280) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if not value:
        return ""
    if len(value) <= limit:
        return value
    return value[: max(1, limit - 1)].rstrip() + "…"


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

    if message.photo:
        parts.append("[Photo attachment]")

    if message.document:
        name = getattr(message.document, "file_name", None) or "document"
        parts.append(f"[Document: {name}]")

    if message.audio:
        name = getattr(message.audio, "file_name", None) or getattr(message.audio, "title", None) or "audio"
        parts.append(f"[Audio: {name}]")

    if message.video:
        name = getattr(message.video, "file_name", None) or "video"
        parts.append(f"[Video: {name}]")

    # Simple attachment indicators
    for attr, label in [("voice", "Voice message"), ("video_note", "Video note")]:
        if getattr(message, attr, None):
            parts.append(f"[{label} — see attachment]")

    return "\n".join(parts) if parts else "[No text content]"


def _extract_reply_context(message: TgMessage) -> str:
    replied = getattr(message, "reply_to_message", None)
    if not replied:
        return ""

    sender = _format_user(getattr(replied, "from_user", None))
    body = _extract_message_content(replied)
    body = _truncate_preview(body, 1200)
    if not body:
        body = "[No text content]"

    return (
        "[User replied to this Telegram message]\n"
        f"From: {sender}\n"
        f"Quoted message:\n{body}"
    )


def _merge_reply_context(message_text: str, reply_context: str) -> str:
    text = (message_text or "").strip() or "[No text content]"
    context_text = (reply_context or "").strip()
    if not context_text:
        return text
    return f"{context_text}\n\n[User message]\n{text}"


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


async def send_telegram_ephemeral_status(context: AgentContext, html_body: str) -> None:
    """Send a short HTML line during tool runs (no TTS). Logs failures; does not raise."""
    try:
        bot_name = context.data.get(CTX_TG_BOT)
        if not bot_name:
            return
        instance = get_bot(bot_name)
        if not instance:
            return
        chat_id = context.data.get(CTX_TG_CHAT_ID)
        if not chat_id:
            return
        async with _temp_bot(
            instance.bot.token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        ) as bot:
            await tc.send_text(
                bot, int(chat_id), html_body, parse_mode=ParseMode.HTML
            )
    except Exception as e:
        PrintStyle.warning(f"Telegram detail status send failed: {format_error(e)}")


# Reply sending (called from process_chain_end extension)

def _progress_settings(bot_cfg: dict) -> dict:
    cfg = (bot_cfg or {}).get("progress") or {}
    try:
        preview_chars = int(cfg.get("live_response_preview_chars", 1200) or 1200)
    except (TypeError, ValueError):
        preview_chars = 1200
    return {
        "enabled": bool(cfg.get("edit_enabled", True)),
        "throttle_ms": int(cfg.get("edit_throttle_ms", 200) or 200),
        "final_in_place": bool(cfg.get("final_in_place", True)),
        "live_response_preview": bool(cfg.get("live_response_preview", True)),
        "native_draft_preview": bool(cfg.get("native_draft_preview", True)),
        "live_response_preview_chars": max(160, min(preview_chars, 4000)),
    }


def _clear_progress_state(context: AgentContext):
    context.data.pop(CTX_TG_PROGRESS_MESSAGE_ID, None)
    context.data.pop(CTX_TG_PROGRESS_LAST_HASH, None)
    context.data.pop(CTX_TG_PROGRESS_LAST_TS, None)
    context.data.pop(CTX_TG_PROGRESS_LINES, None)
    context.data.pop(CTX_TG_PROGRESS_HEADER, None)
    context.data.pop(CTX_TG_STREAM_PREVIEW, None)
    context.data.pop(CTX_TG_STREAM_ACTIVE, None)
    context.data.pop(CTX_TG_STREAM_DRAFT_ID, None)
    context.data.pop(CTX_TG_STREAM_DRAFT_LAST_TS, None)
    context.data.pop(CTX_TG_STREAM_DRAFT_ACTIVE, None)
    context.data.pop(CTX_TG_STREAM_DRAFT_USED, None)
    context.data.pop(CTX_TG_STREAM_DRAFT_DISABLED, None)


def _progress_history_limit(bot_cfg: dict, level: str) -> int:
    cfg = (bot_cfg or {}).get("progress") or {}
    key = "history_limit_verbose" if level == "debug" else "history_limit"
    default = 10 if level == "debug" else 6
    try:
        value = int(cfg.get(key, default) or default)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, 20))


def _progress_status_title(context: AgentContext, bot_cfg: dict, *, done: bool = False) -> str:
    if done:
        return "✅ Completed"
    level = detail_status.effective_detail_level(bot_cfg, context.data)
    if level == "off":
        return "🧠 Working…"
    return "🧠 Working…"


def _progress_line_prefix(line_html: str) -> str:
    text = str(line_html or "")
    if not text:
        return text
    return f"✓ {text}"


def _render_progress_status_html(context: AgentContext, bot_cfg: dict, *, done: bool = False) -> str:
    title = _progress_status_title(context, bot_cfg, done=done)
    lines = list(context.data.get(CTX_TG_PROGRESS_LINES, []) or [])
    level = detail_status.effective_detail_level(bot_cfg, context.data)
    limit = _progress_history_limit(bot_cfg, level)
    if limit and len(lines) > limit:
        lines = lines[-limit:]
    parts = [f"<b>{html.escape(title)}</b>"]
    if lines and level != "off":
        parts.append("")
        parts.extend(_progress_line_prefix(line) for line in lines)
    elif not done and level == "off":
        parts.append("")
        parts.append("<i>Processing your request…</i>")
    preview_html = _render_live_response_preview_html(context, bot_cfg, done=done)
    if preview_html:
        parts.append("")
        parts.append(preview_html)
    return "\n".join(parts)


def _render_live_response_preview_html(
    context: AgentContext, bot_cfg: dict, *, done: bool = False
) -> str:
    if done:
        return ""
    progress_cfg = _progress_settings(bot_cfg)
    if not progress_cfg["live_response_preview"]:
        return ""
    if context.data.get(CTX_TG_STREAM_DRAFT_ACTIVE):
        return ""
    preview = str(context.data.get(CTX_TG_STREAM_PREVIEW, "") or "").strip()
    if not preview:
        return ""
    limit = int(progress_cfg["live_response_preview_chars"])
    if len(preview) > limit:
        preview = "…" + preview[-(limit - 1):]
    return "\n".join([
        "<b>💬 Draft reply…</b>",
        "",
        html.escape(preview),
    ])


def _parse_partial_json_string(payload: str, start: int) -> tuple[str, bool] | None:
    chars: list[str] = []
    i = start
    closed = False
    while i < len(payload):
        ch = payload[i]
        if ch == '"':
            closed = True
            break
        if ch == "\\":
            i += 1
            if i >= len(payload):
                break
            esc = payload[i]
            if esc == "n":
                chars.append("\n")
            elif esc == "r":
                chars.append("\r")
            elif esc == "t":
                chars.append("\t")
            elif esc == "b":
                chars.append("\b")
            elif esc == "f":
                chars.append("\f")
            elif esc in {'"', "\\", "/"}:
                chars.append(esc)
            elif esc == "u":
                hex_code = payload[i + 1 : i + 5]
                if len(hex_code) == 4 and re.fullmatch(r"[0-9a-fA-F]{4}", hex_code):
                    chars.append(chr(int(hex_code, 16)))
                    i += 4
                else:
                    chars.append("u")
            else:
                chars.append(esc)
        else:
            chars.append(ch)
        i += 1
    return "".join(chars), closed


def _extract_partial_json_string_field(payload: str, field_name: str) -> tuple[str, bool] | None:
    if not payload:
        return None
    pattern = rf'"{re.escape(field_name)}"\s*:\s*"'
    match = re.search(pattern, payload)
    if not match:
        return None
    return _parse_partial_json_string(payload, match.end())


def _extract_partial_json_bool_field(payload: str, field_name: str) -> bool | None:
    if not payload:
        return None
    pattern = rf'"{re.escape(field_name)}"\s*:\s*(true|false)'
    match = re.search(pattern, payload, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).lower() == "true"


def _extract_live_response_preview(stream_full: str) -> dict | None:
    raw = str(stream_full or "")
    if not raw:
        return None

    parsed = None
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = None

    tool_name = None
    tool_args = {}
    if isinstance(parsed, dict):
        tool_name = parsed.get("tool_name") or parsed.get("name")
        tool_args = parsed.get("tool_args") if isinstance(parsed.get("tool_args"), dict) else {}
    else:
        tool_match = _extract_partial_json_string_field(raw, "tool_name")
        tool_name = tool_match[0] if tool_match else None

    if tool_name != "response":
        return None

    if tool_args:
        text = tool_args.get("text") or tool_args.get("message") or ""
        break_loop = tool_args.get("break_loop")
        attachments = tool_args.get("attachments") if isinstance(tool_args.get("attachments"), list) else []
    else:
        text_match = _extract_partial_json_string_field(raw, "text") or _extract_partial_json_string_field(raw, "message")
        text = text_match[0] if text_match else ""
        break_loop = _extract_partial_json_bool_field(raw, "break_loop")
        attachments = [True] if re.search(r'"attachments"\s*:\s*\[', raw) else []

    text = str(text or "")
    if not text.strip():
        return None
    if break_loop is False:
        return None
    if attachments:
        return None

    return {
        "text": text,
        "break_loop": break_loop,
    }


def _supports_native_draft_preview(context: AgentContext, bot) -> bool:
    bot_cfg = context.data.get(CTX_TG_BOT_CFG, {}) or {}
    progress_cfg = _progress_settings(bot_cfg)
    if not progress_cfg["enabled"] or not progress_cfg["live_response_preview"]:
        return False
    if not progress_cfg["native_draft_preview"]:
        return False
    if context.data.get(CTX_TG_STREAM_DRAFT_DISABLED):
        return False
    try:
        chat_id = int(context.data.get(CTX_TG_CHAT_ID) or 0)
    except (TypeError, ValueError):
        return False
    if chat_id <= 0:
        return False
    return tc.supports_message_draft(bot)


def _prefer_native_draft_preview(context: AgentContext) -> bool:
    bot_cfg = context.data.get(CTX_TG_BOT_CFG, {}) or {}
    progress_cfg = _progress_settings(bot_cfg)
    if not progress_cfg["enabled"] or not progress_cfg["live_response_preview"]:
        return False
    if not progress_cfg["native_draft_preview"]:
        return False
    if context.data.get(CTX_TG_STREAM_DRAFT_DISABLED):
        return False
    try:
        chat_id = int(context.data.get(CTX_TG_CHAT_ID) or 0)
    except (TypeError, ValueError):
        return False
    if chat_id <= 0:
        return False
    bot_name = context.data.get(CTX_TG_BOT)
    if bot_name:
        instance = get_bot(bot_name)
        if not instance:
            return False
        return tc.supports_message_draft(instance.bot)
    return True


async def _send_telegram_live_draft_preview(
    context: AgentContext,
    preview_text: str,
) -> bool:
    bot_name = context.data.get(CTX_TG_BOT)
    if not bot_name:
        return False
    instance = get_bot(bot_name)
    if not instance:
        return False
    chat_id = context.data.get(CTX_TG_CHAT_ID)
    if not chat_id:
        return False
    if not _supports_native_draft_preview(context, instance.bot):
        return False

    bot_cfg = context.data.get(CTX_TG_BOT_CFG, {}) or {}
    progress_cfg = _progress_settings(bot_cfg)
    throttle_ms = max(0, int(progress_cfg["throttle_ms"]))
    now_ms = int(time.time() * 1000)
    last_ts = int(context.data.get(CTX_TG_STREAM_DRAFT_LAST_TS, 0) or 0)
    if throttle_ms > 0 and (now_ms - last_ts) < throttle_ms:
        return True

    draft_id = int(context.data.get(CTX_TG_STREAM_DRAFT_ID, 0) or 0)
    if draft_id <= 0:
        draft_id = (uuid.uuid4().int % 2147483646) + 1
        context.data[CTX_TG_STREAM_DRAFT_ID] = draft_id

    html_text = tc.md_to_telegram_html(preview_text)
    if len(html_text) > tc.MAX_MESSAGE_LENGTH:
        safe_cut = tc.MAX_MESSAGE_LENGTH - 30
        cut_pos = html_text.rfind("\n", 0, safe_cut)
        if cut_pos < safe_cut // 2:
            cut_pos = safe_cut
        html_text = html_text[:cut_pos] + "\n<i>… truncated</i>"

    try:
        async with _temp_bot(
            instance.bot.token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        ) as reply_bot:
            if not tc.supports_message_draft(reply_bot):
                return False
            ok = await tc.send_message_draft(
                reply_bot,
                int(chat_id),
                draft_id,
                html_text,
                parse_mode=ParseMode.HTML,
            )
        if not ok:
            context.data[CTX_TG_STREAM_DRAFT_DISABLED] = True
            context.data.pop(CTX_TG_STREAM_DRAFT_ACTIVE, None)
            return False
        context.data[CTX_TG_STREAM_DRAFT_LAST_TS] = now_ms
        context.data[CTX_TG_STREAM_DRAFT_ACTIVE] = True
        context.data[CTX_TG_STREAM_DRAFT_USED] = True
        return True
    except Exception as e:
        PrintStyle.error(f"Telegram native draft preview failed: {format_error(e)}")
        context.data[CTX_TG_STREAM_DRAFT_DISABLED] = True
        context.data.pop(CTX_TG_STREAM_DRAFT_ACTIVE, None)
        return False


async def handle_telegram_response_stream_chunk(context: AgentContext, stream_data: dict | None):
    bot_cfg = context.data.get(CTX_TG_BOT_CFG, {}) or {}
    progress_cfg = _progress_settings(bot_cfg)
    if not progress_cfg["enabled"] or not progress_cfg["live_response_preview"]:
        return

    preview = _extract_live_response_preview((stream_data or {}).get("full", ""))
    current_preview = str(context.data.get(CTX_TG_STREAM_PREVIEW, "") or "")

    if not preview:
        return

    next_preview = str(preview.get("text") or "")
    if not next_preview or next_preview == current_preview:
        return

    context.data[CTX_TG_STREAM_PREVIEW] = next_preview
    context.data[CTX_TG_STREAM_ACTIVE] = True
    prefer_native_draft = _prefer_native_draft_preview(context)
    if await _send_telegram_live_draft_preview(context, next_preview):
        return
    if prefer_native_draft:
        return
    html_text = _render_progress_status_html(context, bot_cfg, done=False)
    await send_telegram_progress_update(context, html_text, text_is_html=True)


def handle_telegram_response_stream_end(context: AgentContext):
    context.data.pop(CTX_TG_STREAM_ACTIVE, None)
    context.data.pop(CTX_TG_STREAM_DRAFT_ACTIVE, None)
    context.data.pop(CTX_TG_STREAM_PREVIEW, None)


async def _finalize_progress_message_done(
    reply_bot: Bot,
    context: AgentContext,
    bot_cfg: dict,
    final_keyboard: list[list[dict]] | None = None,
):
    progress_message_id = context.data.get(CTX_TG_PROGRESS_MESSAGE_ID)
    chat_id = context.data.get(CTX_TG_CHAT_ID)
    if not progress_message_id or not chat_id:
        return
    done_html = _render_progress_status_html(context, bot_cfg, done=True)
    if final_keyboard:
        await tc.edit_text_with_keyboard(reply_bot, int(chat_id), int(progress_message_id), done_html, final_keyboard)
    else:
        await tc.edit_text(reply_bot, int(chat_id), int(progress_message_id), done_html)


def _append_progress_line(context: AgentContext, line_html: str, bot_cfg: dict):
    if not line_html:
        return
    lines = list(context.data.get(CTX_TG_PROGRESS_LINES, []) or [])
    lines.append(str(line_html))
    cap = max(4, _progress_history_limit(bot_cfg, "debug") * 2)
    if len(lines) > cap:
        lines = lines[-cap:]
    context.data[CTX_TG_PROGRESS_LINES] = lines


async def _send_initial_progress_status(context: AgentContext):
    bot_cfg = context.data.get(CTX_TG_BOT_CFG, {}) or {}
    html_text = _render_progress_status_html(context, bot_cfg, done=False)
    await send_telegram_progress_update(context, html_text, text_is_html=True)


def _progress_fingerprint(text: str, keyboard: list[list[dict]] | None) -> str:
    payload = {
        "text": text or "",
        "keyboard": keyboard or [],
    }
    return hashlib.sha1(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


async def send_telegram_progress_update(
    context: AgentContext,
    response_text: str,
    keyboard: list[list[dict]] | None = None,
    *,
    text_is_html: bool = False,
) -> str | None:
    """Send or edit an in-progress Telegram status message. Returns error string or None.

    When ``text_is_html`` is True, ``response_text`` is already Telegram HTML (e.g. from
    ``detail_status.format_step_html``) and must not be passed through ``md_to_telegram_html``,
    which would escape ``<b>``, ``<code>``, etc. and show raw tags/entities in the client.
    """
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
    progress_cfg = _progress_settings(bot_cfg)
    reply_to = context.data.get(CTX_TG_REPLY_TO)

    if not response_text:
        return None

    html_text = response_text if text_is_html else tc.md_to_telegram_html(response_text)

    if len(html_text) > tc.MAX_MESSAGE_LENGTH:
        safe_cut = tc.MAX_MESSAGE_LENGTH - 30
        cut_pos = html_text.rfind("\n", 0, safe_cut)
        if cut_pos < safe_cut // 2:
            cut_pos = safe_cut
        html_text = html_text[:cut_pos] + "\n<i>… truncated</i>"

    # Compatibility mode: progress edits disabled -> always send a new message
    if not progress_cfg["enabled"]:
        try:
            async with _temp_bot(
                instance.bot.token,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML),
            ) as reply_bot:
                if keyboard:
                    await tc.send_text_with_keyboard(
                        reply_bot,
                        chat_id,
                        html_text,
                        keyboard,
                        reply_to_message_id=reply_to,
                    )
                else:
                    await tc.send_text(
                        reply_bot,
                        chat_id,
                        html_text,
                        reply_to_message_id=reply_to,
                    )
            return None
        except Exception as e:
            error = format_error(e)
            PrintStyle.error(f"Telegram progress send failed: {error}")
            return error

    fp = _progress_fingerprint(response_text, keyboard)
    if context.data.get(CTX_TG_PROGRESS_LAST_HASH) == fp:
        return None

    now_ms = int(time.time() * 1000)
    last_ts = int(context.data.get(CTX_TG_PROGRESS_LAST_TS, 0) or 0)
    throttle_ms = max(0, int(progress_cfg["throttle_ms"]))
    if throttle_ms > 0 and (now_ms - last_ts) < throttle_ms:
        return None

    try:
        async with _temp_bot(
            instance.bot.token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        ) as reply_bot:
            message_id = context.data.get(CTX_TG_PROGRESS_MESSAGE_ID)
            sent_or_edited = False

            if message_id:
                if keyboard:
                    sent_or_edited = await tc.edit_text_with_keyboard(
                        reply_bot, chat_id, int(message_id), html_text, keyboard
                    )
                else:
                    sent_or_edited = await tc.edit_text(
                        reply_bot, chat_id, int(message_id), html_text
                    )

            if not sent_or_edited:
                if keyboard:
                    new_id = await tc.send_text_with_keyboard(
                        reply_bot,
                        chat_id,
                        html_text,
                        keyboard,
                        reply_to_message_id=reply_to,
                    )
                else:
                    new_id = await tc.send_text(
                        reply_bot,
                        chat_id,
                        html_text,
                        reply_to_message_id=reply_to,
                    )
                if new_id:
                    context.data[CTX_TG_PROGRESS_MESSAGE_ID] = int(new_id)
                    sent_or_edited = True

            if sent_or_edited:
                context.data[CTX_TG_PROGRESS_LAST_HASH] = fp
                context.data[CTX_TG_PROGRESS_LAST_TS] = now_ms

        return None

    except Exception as e:
        error = format_error(e)
        PrintStyle.error(f"Telegram progress update failed: {error}")
        return error


async def send_telegram_reply(
    context: AgentContext,
    response_text: str,
    attachments: list[str] | None = None,
    keyboard: list[list[dict]] | None = None,
    voice_text: str | None = None,
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
    progress_cfg = _progress_settings(bot_cfg)

    # Per-response overrides set by the response-tool (tool_execute_after extension).
    # Transient — popped here. The agent may only DE-ESCALATE (force→auto→off),
    # never escalate above the effective user/admin mode.
    override_mode = str(context.data.pop(CTX_TG_VOICE_REPLY_MODE, "") or "").lower()
    context.data.pop(CTX_TG_FORCE_VOICE_REPLY, None)

    effective = speech.effective_voice_reply_mode(bot_cfg, context.data)

    _MODE_RANK = {"off": 0, "auto": 1, "force": 2}
    if override_mode in _MODE_RANK and _MODE_RANK[override_mode] < _MODE_RANK.get(effective, 0):
        mode = override_mode
    else:
        mode = effective

    last_input_was_voice = bool(context.data.get(CTX_TG_LAST_INPUT_WAS_VOICE, False))
    want_voice = mode == "force" or (mode == "auto" and last_input_was_voice)

    reply_to = context.data.get(CTX_TG_REPLY_TO)

    tts_raw = ((voice_text or "").strip() or (response_text or "").strip())

    tts_on = speech.tts_enabled(bot_cfg)
    if want_voice and tts_raw and not tts_on:
        PrintStyle.info(
            "Telegram TTS skipped: speech.tts.enabled is false for this bot (check plugin config / project scope)."
        )
    elif want_voice and not tts_raw:
        PrintStyle.info("Telegram TTS skipped: empty text for TTS.")
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
            if want_voice and tts_raw and tts_on:
                try:
                    max_chars = max(100, int(reply_cfg["max_chars"]))
                    tts_payload = tts_raw[:max_chars]
                    await tc.send_record_voice(reply_bot, chat_id)
                    voice_file, _meta = await asyncio.to_thread(speech.synthesize_to_voice_file, bot_cfg, tts_payload)
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

            also = speech.effective_also_send_text(bot_cfg, context.data)
            quick_actions = speech.quick_actions_settings(bot_cfg)
            # If the agent only set voice_text (TTS) and left text empty, response_text is
            # empty but users still expect a text bubble when also_send_text is on.
            text_body = (response_text or "").strip()
            if not text_body and (voice_text or "").strip():
                text_body = (voice_text or "").strip()

            context.data[CTX_TG_LAST_TEXT_RESPONSE] = text_body
            response_token = ""
            if text_body:
                response_token = uuid.uuid4().hex[:12]
                context.data[CTX_TG_LAST_TEXT_RESPONSE_TOKEN] = response_token
            else:
                context.data.pop(CTX_TG_LAST_TEXT_RESPONSE_TOKEN, None)

            quick_action_keyboard = None
            if (
                sent_voice
                and _voice_conversation_mode(context) == "voice_only"
                and text_body
                and quick_actions.get("enabled", True)
                and quick_actions.get("show_text", True)
            ):
                quick_action_keyboard = _show_text_quick_action_keyboard(response_token)

            final_keyboard = _append_inline_keyboard(keyboard, quick_action_keyboard)
            used_native_draft = bool(context.data.get(CTX_TG_STREAM_DRAFT_USED))

            should_send_text = bool(text_body) and (
                final_keyboard is not None or not sent_voice or also
            )
            if should_send_text:
                html_text = tc.md_to_telegram_html(text_body)
                progress_message_id = context.data.get(CTX_TG_PROGRESS_MESSAGE_ID)
                use_final_edit = bool(
                    progress_cfg["enabled"]
                    and progress_cfg["final_in_place"]
                    and progress_message_id
                    and not attachments
                    and not used_native_draft
                )

                edited = False
                if use_final_edit:
                    if final_keyboard:
                        edited = await tc.edit_text_with_keyboard(
                            reply_bot, chat_id, int(progress_message_id), html_text, final_keyboard,
                        )
                    else:
                        edited = await tc.edit_text(
                            reply_bot, chat_id, int(progress_message_id), html_text,
                        )

                if not edited:
                    if final_keyboard:
                        await tc.send_text_with_keyboard(reply_bot, chat_id, html_text, final_keyboard, reply_to_message_id=reply_to)
                    else:
                        await tc.send_text(reply_bot, chat_id, html_text, reply_to_message_id=reply_to)
                    if used_native_draft and progress_cfg["enabled"] and progress_message_id:
                        await _finalize_progress_message_done(reply_bot, context, bot_cfg, final_keyboard)
            else:
                progress_message_id = context.data.get(CTX_TG_PROGRESS_MESSAGE_ID)
                if progress_cfg["enabled"] and progress_cfg["final_in_place"] and progress_message_id:
                    await _finalize_progress_message_done(reply_bot, context, bot_cfg, final_keyboard)

            _clear_progress_state(context)

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


async def _send_with_temp_bot(
    token: str,
    chat_id: int,
    text: str,
    parse_mode: str | ParseMode | None = None,
    keyboard: list[list[dict]] | None = None,
):
    """Send text using a temporary Bot to avoid cross-event-loop session issues."""
    async with _temp_bot(token) as bot:
        if keyboard:
            await tc.send_text_with_keyboard(
                bot, chat_id, text, keyboard, parse_mode=parse_mode
            )
        else:
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
