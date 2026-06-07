"""Telegram tool-run detail levels: off / info / smart / debug (bot config + session override)."""

from __future__ import annotations

import os
import html
import importlib
import json
import re
from typing import Any

DETAIL_LEVELS = frozenset({"off", "info", "smart", "debug"})
_DEFAULT_DETAIL_LEVEL = "info"
_DEFAULT_EXECUTE_BEFORE = True

_DEFAULT_ICONS: dict[str, str] = {
    "memory_load": "\U0001f9e0",
    "memory_save": "\U0001f9e0",
    "memory_forget": "\U0001f9e0",
    "memory_query": "\U0001f9e0",
    "knowledge_tool": "\U0001f4da",
    "code_execution": "\U0001f4bb",
    "call_subordinate": "\U0001f91d",
    "response": "\u2705",
    "wait": "\u23f3",
    "notify_user": "\U0001f4e3",
    "a2a": "\U0001f517",
}

_PREFIX_ICONS: list[tuple[str, str]] = [
    ("memory", "\U0001f9e0"),
    ("knowledge", "\U0001f4da"),
    ("text_editor", "\U0001f4dd"),
    ("search_engine", "\U0001f50e"),
    ("browser", "\U0001f310"),
    ("document", "\U0001f4c4"),
    ("vision", "\U0001f5bc"),
    ("code_execution", "\U0001f4bb"),
    ("skills", "\U0001f4e6"),
]

_DEFAULT_MAX_BODY_CHARS = 3200
_REDACTED = "[REDACTED]"
_SENSITIVE_KEY_TOKENS = (
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "token",
    "password",
    "passwd",
    "pass",
    "secret",
    "authorization",
    "auth",
    "cookie",
    "session",
    "client_secret",
    "private_key",
    "ssh_key",
    "bearer",
    "webhook_secret",
    "x_api_key",
)
_SENSITIVE_ENV_RE = re.compile(
    r"\b([A-Z0-9_]*(?:PASS|PASSWORD|TOKEN|SECRET|API_KEY|APIKEY|AUTH|COOKIE|SESSION)[A-Z0-9_]*)\s*=\s*([^\s'\"`]+|'[^']*'|\"[^\"]*\")"
)
_HEADER_REDACT_RE = re.compile(
    r"(?i)\b(authorization|x-api-key|xi-api-key|proxy-authorization)\b\s*[:=]\s*([^\r\n,;]+)"
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[^\s\"'<>()]+")
_BASIC_AUTH_RE = re.compile(r"(?i)(^|\s)(-u\s+)([^\s:]+):([^\s]+)")
_URL_CREDS_RE = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)([^\s/@:]+):([^\s/@]+)@")
_QUERY_SECRET_RE = re.compile(
    r"(?i)([?&](?:access_token|refresh_token|token|api[_-]?key|apikey|password|passwd|pass|secret|auth|authorization|client_secret|webhook_secret)=)([^&#\s]+)"
)
_GENERIC_SECRET_ASSIGN_RE = re.compile(
    r"(?i)\b(access_token|refresh_token|token|api[_-]?key|apikey|password|passwd|pass|secret|auth|authorization|client_secret|webhook_secret)\b\s*[:=]\s*([^\s,;&'\"`]+|'[^']*'|\"[^\"]*\")"
)


def _normalize_key(key: Any) -> str:
    return str(key).strip().lower().replace("-", "_")


def _is_sensitive_key(key: Any) -> bool:
    norm = _normalize_key(key)
    return any(token in norm for token in _SENSITIVE_KEY_TOKENS)


def _resolve_secret_reference(value: str) -> str:
    value = str(value or "")
    if value.startswith("${") and value.endswith("}") and len(value) > 3:
        return os.getenv(value[2:-1], "")
    if value.startswith("os.environ/"):
        return os.getenv(value.split("/", 1)[1], "")
    return value


def _collect_secret_values_from_obj(obj: Any, out: set[str]) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if _is_sensitive_key(key):
                _collect_scalar_secret_values(value, out)
            _collect_secret_values_from_obj(value, out)
        return
    if isinstance(obj, (list, tuple, set)):
        for item in obj:
            _collect_secret_values_from_obj(item, out)


def _collect_scalar_secret_values(value: Any, out: set[str]) -> None:
    if isinstance(value, dict):
        _collect_secret_values_from_obj(value, out)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            _collect_scalar_secret_values(item, out)
        return
    if value is None:
        return
    text = str(value).strip()
    if not text:
        return
    resolved = _resolve_secret_reference(text).strip()
    candidate = resolved or text
    if len(candidate) >= 6:
        out.add(candidate)


def collect_known_secret_values(bot_cfg: dict, agent: Any | None = None) -> list[str]:
    found: set[str] = set()
    _collect_secret_values_from_obj(bot_cfg or {}, found)

    if agent is not None:
        try:
            mc = importlib.import_module("plugins._model_config.helpers.model_config")

            _collect_secret_values_from_obj(mc.get_chat_model_config(agent) or {}, found)
            _collect_secret_values_from_obj(mc.get_utility_model_config(agent) or {}, found)
        except Exception:
            pass

    return sorted(found, key=len, reverse=True)


def _redact_sensitive_text(text: str, known_secret_values: list[str] | None = None) -> str:
    safe = str(text)
    for secret in known_secret_values or []:
        if secret:
            safe = safe.replace(secret, _REDACTED)

    safe = _HEADER_REDACT_RE.sub(lambda m: f"{m.group(1)}: {_REDACTED}", safe)
    safe = _BEARER_RE.sub(f"Bearer {_REDACTED}", safe)
    safe = _BASIC_AUTH_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}:{_REDACTED}", safe)
    safe = _URL_CREDS_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}:{_REDACTED}@", safe)
    safe = _QUERY_SECRET_RE.sub(lambda m: f"{m.group(1)}{_REDACTED}", safe)
    safe = _GENERIC_SECRET_ASSIGN_RE.sub(lambda m: f"{m.group(1)}={_REDACTED}", safe)
    safe = _SENSITIVE_ENV_RE.sub(lambda m: f"{m.group(1)}={_REDACTED}", safe)
    return safe


def redact_sensitive(value: Any, known_secret_values: list[str] | None = None) -> Any:
    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(key):
                redacted[key] = _REDACTED
            else:
                redacted[key] = redact_sensitive(item, known_secret_values)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive(item, known_secret_values) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive(item, known_secret_values) for item in value]
    if isinstance(value, set):
        return [redact_sensitive(item, known_secret_values) for item in sorted(value, key=str)]
    if isinstance(value, str):
        return _redact_sensitive_text(value, known_secret_values)
    return value


def normalize_detail_level(value: Any) -> str:
    if value is None:
        return _DEFAULT_DETAIL_LEVEL
    s = str(value).strip().lower()
    if s == "verbose":
        return "debug"
    return s if s in DETAIL_LEVELS else "off"


def detail_level_display(level: str) -> str:
    """User-facing label: internal level ``debug`` is shown as ``verbose``."""
    s = normalize_detail_level(level)
    if s == "debug":
        return "verbose"
    return s


def effective_detail_level(bot_cfg: dict, ctx_data: dict) -> str:
    from usr.plugins.telegram_integration_voice.helpers.constants import (
        CTX_TG_DETAIL_LEVEL_SESSION,
    )

    sess = ctx_data.get(CTX_TG_DETAIL_LEVEL_SESSION)
    if sess is not None and str(sess).strip() != "":
        return normalize_detail_level(sess)
    return normalize_detail_level(bot_cfg.get("telegram_detail_level"))


def normalize_execute_before_enabled(value: Any) -> bool:
    if value is None:
        return _DEFAULT_EXECUTE_BEFORE
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes", "on", "enable", "enabled")


def effective_execute_before_enabled(bot_cfg: dict, ctx_data: dict) -> bool:
    from usr.plugins.telegram_integration_voice.helpers.constants import (
        CTX_TG_DETAIL_BEFORE_SESSION,
    )

    sess = ctx_data.get(CTX_TG_DETAIL_BEFORE_SESSION)
    if sess is not None and str(sess).strip() != "":
        return normalize_execute_before_enabled(sess)
    return normalize_execute_before_enabled(bot_cfg.get("telegram_detail_execute_before"))


def detail_throttle_sec(bot_cfg: dict, level: str) -> float:
    if level == "off":
        return 0.0
    if level == "info":
        key = "telegram_detail_info_min_interval_sec"
        default = 5.0
    else:
        key = "telegram_detail_debug_min_interval_sec"
        default = 1.5
    try:
        v = float(bot_cfg.get(key, default) or default)
    except (TypeError, ValueError):
        v = default
    return max(0.3, min(v, 120.0))


def detail_exclude_set(bot_cfg: dict) -> set[str]:
    raw = bot_cfg.get("telegram_detail_exclude_tools")
    if not isinstance(raw, list):
        return set()
    return {str(x).strip() for x in raw if str(x).strip()}


def detail_tool_labels(bot_cfg: dict) -> dict[str, str]:
    raw = bot_cfg.get("telegram_detail_tool_labels")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        ks, vs = str(k).strip(), str(v).strip()
        if ks and vs:
            out[ks] = vs
    return out


def _icons_enabled(bot_cfg: dict) -> bool:
    v = bot_cfg.get("telegram_detail_icons_enabled")
    if v is None:
        return True
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() not in ("false", "0", "no", "off")


def _icon_overrides(bot_cfg: dict) -> dict[str, str]:
    raw = bot_cfg.get("telegram_detail_tool_icons")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        ks, vs = str(k).strip(), str(v).strip()
        if ks and vs:
            out[ks] = vs
    return out


def step_icon_for_tool(name: str, bot_cfg: dict) -> str:
    """Resolve a single emoji for *name* (tool_name from A0 hook).

    Lookup order: config overrides -> exact built-in -> prefix before ':' ->
    prefix match against _PREFIX_ICONS -> fallback.
    """
    if not _icons_enabled(bot_cfg):
        return ""

    overrides = _icon_overrides(bot_cfg)

    if name in overrides:
        return overrides[name]

    prefix = name.split(":")[0] if ":" in name else name

    if prefix in overrides:
        return overrides[prefix]

    if name in _DEFAULT_ICONS:
        return _DEFAULT_ICONS[name]
    if prefix in _DEFAULT_ICONS:
        return _DEFAULT_ICONS[prefix]

    for pfx, icon in _PREFIX_ICONS:
        if prefix.startswith(pfx):
            return icon

    return "\U0001f539"


def _max_body_chars(bot_cfg: dict) -> int:
    try:
        v = int(bot_cfg.get("telegram_detail_max_body_chars", _DEFAULT_MAX_BODY_CHARS) or _DEFAULT_MAX_BODY_CHARS)
    except (TypeError, ValueError):
        v = _DEFAULT_MAX_BODY_CHARS
    return max(200, min(v, 3800))


def _truncate_body(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = limit - 40
    if cut < 20:
        cut = 20
    removed = len(text) - cut
    return text[:cut] + f"\n\n<< {removed} chars omitted >>"


async def _format_step_html_smart(
    tool_name: str,
    bot_cfg: dict,
    *,
    tool_args: dict | None = None,
    known_secret_values: list[str] | None = None,
    agent: Any | None = None,
) -> str:
    labels = detail_tool_labels(bot_cfg)
    label = labels.get(tool_name, tool_name)
    icon = step_icon_for_tool(tool_name, bot_cfg)
    icon_prefix = f"{icon} " if icon else ""
    safe_label = html.escape(str(label))

    if agent is None or not hasattr(agent, "call_utility_model"):
        return f"{icon_prefix}{safe_label}"

    safe_tool_args = redact_sensitive(tool_args, known_secret_values) if tool_args is not None else None
    try:
        args_json = json.dumps(safe_tool_args, ensure_ascii=False, sort_keys=True, indent=2) if safe_tool_args is not None else "{}"
    except Exception:
        args_json = _redact_sensitive_text(str(safe_tool_args), known_secret_values)
    args_json = _truncate_body(args_json, min(_max_body_chars(bot_cfg), 1200))

    system = (
        "You summarize tool activity for a Telegram progress bubble. "
        "Return exactly one short plain-text line, max 160 characters. "
        "Focus on the user-visible intent of the tool call. "
        "Do not mention JSON, redaction, secrets, or internal formatting."
    )
    message = (
        f"Tool: {tool_name}\n"
        f"Label: {label}\n"
        f"Arguments:\n{args_json}\n\n"
        "Write one concise status line for the user."
    )
    try:
        summary = await agent.call_utility_model(system=system, message=message, background=True)
    except Exception:
        summary = ""

    text = str(summary or "").strip()
    if not text:
        return f"{icon_prefix}{safe_label}"
    text = re.sub(r"\s+", " ", text).strip(" -•\n\t")
    if len(text) > 160:
        text = text[:157].rstrip() + "..."
    return f"{icon_prefix}{html.escape(text)}"


def _response_message_text(response: Any | None) -> str:
    if response is None:
        return ""
    message = getattr(response, "message", response)
    return str(message or "").strip()


def _response_looks_like_error(response: Any | None, error_text: str = "") -> bool:
    if error_text.strip():
        return True
    text = _response_message_text(response).lower()
    if not text:
        return False
    prefixes = (
        "error:",
        "failed:",
        "failure:",
        "exception:",
    )
    tokens = (
        " failed",
        " failure",
        " exception",
        " traceback",
        "timed out",
        "timeout",
        "invalid ",
        "not found",
        "could not ",
        "unable to ",
    )
    if text.startswith(prefixes):
        return True
    return any(token in text for token in tokens)


async def _format_step_result_html_smart(
    tool_name: str,
    bot_cfg: dict,
    *,
    tool_args: dict | None = None,
    response: Any | None = None,
    error_text: str = "",
    known_secret_values: list[str] | None = None,
    agent: Any | None = None,
) -> str:
    labels = detail_tool_labels(bot_cfg)
    label = labels.get(tool_name, tool_name)
    icon = step_icon_for_tool(tool_name, bot_cfg)
    icon_prefix = f"{icon} " if icon else ""
    safe_label = html.escape(str(label))

    if agent is None or not hasattr(agent, "call_utility_model"):
        status = "failed" if _response_looks_like_error(response, error_text) else "done"
        return f"{icon_prefix}{safe_label} {status}"

    safe_tool_args = redact_sensitive(tool_args, known_secret_values) if tool_args is not None else None
    result_text = error_text.strip() or _response_message_text(response)
    safe_result = _redact_sensitive_text(result_text, known_secret_values)
    body_limit = min(_max_body_chars(bot_cfg), 1200)
    try:
        args_json = json.dumps(safe_tool_args, ensure_ascii=False, sort_keys=True, indent=2) if safe_tool_args is not None else "{}"
    except Exception:
        args_json = _redact_sensitive_text(str(safe_tool_args), known_secret_values)
    args_json = _truncate_body(args_json, max(200, body_limit // 2))
    safe_result = _truncate_body(safe_result, max(200, body_limit // 2))

    outcome = "failed" if _response_looks_like_error(response, error_text) else "completed"
    system = (
        "You summarize completed tool activity for a Telegram progress bubble. "
        "Return exactly one short plain-text line, max 160 characters. "
        "Focus on the user-visible outcome, not implementation details. "
        "Do not mention JSON, redaction, secrets, or internal formatting."
    )
    message = (
        f"Tool: {tool_name}\n"
        f"Label: {label}\n"
        f"Outcome: {outcome}\n"
        f"Arguments:\n{args_json}\n\n"
        f"Result:\n{safe_result or '(empty result)'}\n\n"
        "Write one concise status line for the user."
    )
    try:
        summary = await agent.call_utility_model(system=system, message=message, background=True)
    except Exception:
        summary = ""

    text = str(summary or "").strip()
    if not text:
        return f"{icon_prefix}{safe_label} {outcome}"
    text = re.sub(r"\s+", " ", text).strip(" -•\n\t")
    if len(text) > 160:
        text = text[:157].rstrip() + "..."
    return f"{icon_prefix}{html.escape(text)}"


def format_step_html(
    tool_name: str,
    bot_cfg: dict,
    *,
    level: str = "info",
    tool_args: dict | None = None,
    known_secret_values: list[str] | None = None,
    agent: Any | None = None,
) -> str | Any:
    """Format tool-step status with icon + label.

    - info: icon + label (single line)
    - smart: utility-model short summary based on redacted tool args
    - debug: icon + tool name (bold) + optional truncated args payload
    """
    labels = detail_tool_labels(bot_cfg)
    label = labels.get(tool_name, tool_name)
    icon = step_icon_for_tool(tool_name, bot_cfg)
    icon_prefix = f"{icon} " if icon else ""

    if level == "smart":
        return _format_step_html_smart(
            tool_name,
            bot_cfg,
            tool_args=tool_args,
            known_secret_values=known_secret_values,
            agent=agent,
        )

    if level != "debug":
        safe = html.escape(str(label))
        return f"{icon_prefix}{safe}"

    safe_name = html.escape(str(tool_name))
    parts = [f"{icon_prefix}<b>{safe_name}</b>"]

    if tool_args is not None:
        safe_tool_args = redact_sensitive(tool_args, known_secret_values)
        try:
            args_json = json.dumps(safe_tool_args, ensure_ascii=False, sort_keys=True, indent=2)
        except Exception:
            args_json = _redact_sensitive_text(str(safe_tool_args), known_secret_values)
        max_chars = _max_body_chars(bot_cfg)
        args_json = _truncate_body(args_json, max_chars)
        parts.append(f"<blockquote><code>{html.escape(args_json)}</code></blockquote>")

    return "\n".join(parts)


def format_step_result_html(
    tool_name: str,
    bot_cfg: dict,
    *,
    level: str = "info",
    tool_args: dict | None = None,
    response: Any | None = None,
    error_text: str = "",
    known_secret_values: list[str] | None = None,
    agent: Any | None = None,
) -> str | Any:
    """Format the completion-time tool status line.

    - info: icon + label + done/failed
    - smart: utility-model summary using args + result text
    - debug: icon + tool name + args + truncated result payload
    """
    labels = detail_tool_labels(bot_cfg)
    label = labels.get(tool_name, tool_name)
    icon = step_icon_for_tool(tool_name, bot_cfg)
    icon_prefix = f"{icon} " if icon else ""
    is_error = _response_looks_like_error(response, error_text)

    if level == "smart":
        return _format_step_result_html_smart(
            tool_name,
            bot_cfg,
            tool_args=tool_args,
            response=response,
            error_text=error_text,
            known_secret_values=known_secret_values,
            agent=agent,
        )

    if level != "debug":
        safe = html.escape(str(label))
        suffix = "failed" if is_error else "done"
        return f"{icon_prefix}{safe} {suffix}"

    safe_name = html.escape(str(tool_name))
    status = "failed" if is_error else "done"
    parts = [f"{icon_prefix}<b>{safe_name}</b> <i>{status}</i>"]

    result_text = error_text.strip() or _response_message_text(response)
    max_chars = _max_body_chars(bot_cfg)
    shared_budget = max_chars
    args_budget = shared_budget
    result_budget = shared_budget
    if tool_args is not None and result_text:
        args_budget = max(200, shared_budget // 2)
        result_budget = max(200, shared_budget - args_budget)

    if tool_args is not None:
        safe_tool_args = redact_sensitive(tool_args, known_secret_values)
        try:
            args_json = json.dumps(safe_tool_args, ensure_ascii=False, sort_keys=True, indent=2)
        except Exception:
            args_json = _redact_sensitive_text(str(safe_tool_args), known_secret_values)
        args_json = _truncate_body(args_json, args_budget)
        parts.append(f"<blockquote><code>{html.escape(args_json)}</code></blockquote>")

    if result_text:
        result_body = _truncate_body(
            _redact_sensitive_text(result_text, known_secret_values),
            result_budget,
        )
        parts.append(f"<blockquote>{html.escape(result_body)}</blockquote>")

    return "\n".join(parts)
