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
        "Browse and delete sessions",
        "/session [search …] — browse saved sessions, search, and open a session to delete it",
    ),
    (
        "title",
        "Rename current session",
        "/title [new name|auto] — set a manual session title or reset to automatic naming",
    ),
    (
        "actions",
        "Reply actions",
        "/actions [on|off] — toggle the per-reply More menu for this session",
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
        "/detail off|info|smart|verbose — no arg = status + buttons (debug = verbose)",
    ),
    (
        "detail_before",
        "Tool start updates",
        "/detail_before [on|off] — toggle execute-before tool updates; no arg = status + buttons",
    ),
    (
        "voice",
        "Voice reply mode",
        "/voice [voice_only|voice_text|auto|text_only|off] — auto speaks only after a voice message; no arg = status + buttons",
    ),
    (
        "rich",
        "Rich message rendering",
        "/rich [on|off] — native rendering for tables, headings, task lists and math; no arg = status + buttons",
    ),
    (
        "ux",
        "Enhanced reply UX",
        "/ux [on|off|rich|drafts|copy] — rich rendering, native drafts, and copy buttons; no arg = status + buttons",
    ),
    (
        "suggest",
        "Suggested replies",
        "/suggest [on|off] — tap-to-send follow-up suggestions under replies; no arg = status + buttons",
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
        "shortcut",
        "Reply shortcuts",
        "/shortcut [shorter|longer|summary] — no arg = buttons; rewrite the last answer or summarize the active session",
    ),
    (
        "stop",
        "Stop task",
        "/stop — abort the running agent task",
    ),
    (
        "reload",
        "Reload Agent Zero",
        "/reload — reload Agent Zero after admin confirmation",
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


# German command-menu descriptions (shown to Telegram clients with a German
# UI via setMyCommands(language_code="de")). Fallback: English description.
COMMAND_MENU_DE: dict[str, str] = {
    "help": "Befehlsliste",
    "start": "Begrüßung und Session",
    "status": "Agent-Status",
    "clear": "Chat zurücksetzen",
    "newchat": "Neue Chat-Session",
    "session": "Sessions durchsuchen und löschen",
    "title": "Aktuelle Session umbenennen",
    "actions": "Antwort-Aktionen",
    "topic": "Topic öffnen oder benennen",
    "optimize_output": "Antwortstil (Sprache/Text)",
    "detail": "Tool-Status-Detailgrad",
    "detail_before": "Updates beim Tool-Start",
    "voice": "Sprachantwort-Modus",
    "rich": "Rich-Nachrichten-Rendering",
    "ux": "Erweiterte Antwort-UX",
    "suggest": "Antwortvorschläge",
    "retry": "Letzte Nachricht wiederholen",
    "undo": "Letzten Austausch entfernen",
    "compact": "Kontext komprimieren",
    "shortcut": "Antwort-Shortcuts",
    "stop": "Aufgabe stoppen",
    "reload": "Agent Zero neu laden",
    "project": "Projekt anzeigen oder wechseln",
    "model": "Modell-Preset anzeigen/wechseln",
    "pause": "Agent pausieren",
    "resume": "Agent fortsetzen",
}


def get_bot_commands(language: str = "en") -> list[BotCommand]:
    """Commands shown in the Telegram command menu (order preserved)."""
    commands = []
    for cmd, desc, _ in COMMAND_ROWS:
        if language == "de":
            desc = COMMAND_MENU_DE.get(cmd, desc)
        commands.append(BotCommand(command=cmd, description=desc[:256]))
    return commands


async def register_bot_command_menu(bot: Bot) -> None:
    """Call Telegram setMyCommands so the client shows the command menu.

    Registers the English menu as default plus a German variant scoped to
    clients with a German UI (Telegram picks per user automatically).
    """
    try:
        await bot.set_my_commands(get_bot_commands())
    except Exception as e:
        PrintStyle.warning(f"Telegram set_my_commands failed: {format_error(e)}")
    try:
        await bot.set_my_commands(get_bot_commands("de"), language_code="de")
    except Exception as e:
        PrintStyle.warning(f"Telegram set_my_commands (de) failed: {format_error(e)}")


_HELP_INTRO = {
    "en": "Reply and voice modes apply to this chat and switch anytime with the commands below.",
    "de": "Antwort- und Sprachmodi gelten für diesen Chat und lassen sich jederzeit mit den Befehlen unten umschalten.",
}


def format_help_text(language: str = "en") -> str:
    """Plain-text body for /help replies."""
    lines = [
        _HELP_INTRO.get(language) or _HELP_INTRO["en"],
        "",
        "Commands:" if language != "de" else "Befehle:",
    ]
    if language == "de":
        for cmd, desc, _ in COMMAND_ROWS:
            lines.append(f"/{cmd} — {COMMAND_MENU_DE.get(cmd, desc)}")
    else:
        for _, _, help_line in COMMAND_ROWS:
            lines.append(help_line)
    return "\n".join(lines)
