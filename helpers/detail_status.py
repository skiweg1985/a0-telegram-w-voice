"""Telegram tool-run detail levels: off / info / debug (bot config + session override)."""

from __future__ import annotations

import html
import json
from typing import Any

DETAIL_LEVELS = frozenset({"off", "info", "debug"})

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


def normalize_detail_level(value: Any) -> str:
    s = str(value if value is not None else "off").strip().lower()
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


def format_step_html(
    tool_name: str,
    bot_cfg: dict,
    *,
    level: str = "info",
    tool_args: dict | None = None,
) -> str:
    """Format tool-step status with icon + label.

    - info: icon + label (single line)
    - debug: icon + tool name (bold) + optional truncated args payload
    """
    labels = detail_tool_labels(bot_cfg)
    label = labels.get(tool_name, tool_name)
    icon = step_icon_for_tool(tool_name, bot_cfg)
    icon_prefix = f"{icon} " if icon else ""

    if level != "debug":
        safe = html.escape(str(label))
        return f"{icon_prefix}{safe}"

    safe_name = html.escape(str(tool_name))
    parts = [f"{icon_prefix}<b>{safe_name}</b>"]

    if tool_args is not None:
        try:
            args_json = json.dumps(tool_args, ensure_ascii=False, sort_keys=True, indent=2)
        except Exception:
            args_json = str(tool_args)
        max_chars = _max_body_chars(bot_cfg)
        args_json = _truncate_body(args_json, max_chars)
        parts.append(f"<blockquote><code>{html.escape(args_json)}</code></blockquote>")

    return "\n".join(parts)
