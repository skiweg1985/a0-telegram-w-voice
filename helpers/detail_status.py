"""Telegram tool-run detail levels: off / info / debug (bot config + session override)."""

from __future__ import annotations

import html
from typing import Any

DETAIL_LEVELS = frozenset({"off", "info", "debug"})


def normalize_detail_level(value: Any) -> str:
    s = str(value if value is not None else "off").strip().lower()
    return s if s in DETAIL_LEVELS else "off"


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


def format_step_html(tool_name: str, bot_cfg: dict) -> str:
    """Single-line HTML status: safe label only, no tool args."""
    labels = detail_tool_labels(bot_cfg)
    label = labels.get(tool_name, tool_name)
    safe = html.escape(str(label))
    return f"Step: {safe}"
