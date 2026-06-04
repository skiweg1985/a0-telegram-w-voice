"""
Telegram bot commands: single source for BotFather-style menu and /help text.
Descriptions must stay short (Telegram menu limit).
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.types import BotCommand

from helpers.errors import format_error
from helpers.print_style import PrintStyle

# (command, menu_description, help_line_for_users)
COMMAND_ROWS: list[tuple[str, str, str]] = [
    (
        "help",
        "Command list",
        "/help — list commands",
    ),
    (
        "start",
        "Welcome and session",
        "/start — welcome; ensures a session",
    ),
    (
        "status",
        "Agent status",
        "/status — model, tokens, project, TTS/STT, run state",
    ),
    (
        "clear",
        "Reset chat",
        "/clear — reset conversation in the current session",
    ),
    (
        "newchat",
        "New chat session",
        "/newchat — new session; old chat stays in browser UI",
    ),
    (
        "session",
        "Browse saved sessions",
        "/session [id|search …] — browse, search, or switch saved sessions for this Telegram chat",
    ),
    (
        "topic",
        "Open or name a topic",
        "/topic [name] — open a named topic or start a new one; no arg lists topics",
    ),
    (
        "optimize_output",
        "Answer style (voice/text)",
        "/optimize_output voice|text|auto|off — no arg = status + buttons",
    ),
    (
        "detail",
        "Tool status detail",
        "/detail off|info|verbose — no arg = status + buttons (debug = verbose)",
    ),
    (
        "voice",
        "Voice reply mode",
        "/voice [voice_only|voice_text|auto|text_only|off] — auto speaks only after a voice message; no arg = status + buttons",
    ),
    (
        "retry",
        "Redo last message",
        "/retry — re-run your last message",
    ),
    (
        "undo",
        "Remove last exchange",
        "/undo — drop the last message and its reply from history",
    ),
    (
        "compact",
        "Compress context",
        "/compact — shrink history (utility LLM)",
    ),
    (
        "stop",
        "Stop task",
        "/stop — abort the running agent task",
    ),
    (
        "project",
        "Show or switch project",
        "/project [name] — list + buttons or switch by name",
    ),
    (
        "model",
        "Show or switch preset",
        "/model [preset] — no arg: info + preset buttons if allowed",
    ),
    (
        "pause",
        "Pause agent",
        "/pause — pause until /resume",
    ),
    (
        "resume",
        "Resume agent",
        "/resume — continue after /pause",
    ),
]


def get_bot_commands() -> list[BotCommand]:
    """Commands shown in the Telegram command menu (order preserved)."""
    return [
        BotCommand(command=cmd, description=desc[:256])
        for cmd, desc, _ in COMMAND_ROWS
    ]


async def register_bot_command_menu(bot: Bot) -> None:
    """Call Telegram setMyCommands so the client shows the command menu."""
    try:
        await bot.set_my_commands(get_bot_commands())
    except Exception as e:
        PrintStyle.warning(f"Telegram set_my_commands failed: {format_error(e)}")


def format_help_text() -> str:
    """Plain-text body for /help replies."""
    lines = [
        "Reply and voice modes apply to this chat and switch anytime with the commands below.",
        "",
        "Commands:",
    ]
    for _, _, help_line in COMMAND_ROWS:
        lines.append(help_line)
    return "\n".join(lines)
