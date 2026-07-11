"""Localized user-facing copy for the Telegram chat surface.

Per-bot config key ``language: en|de`` (default ``en``). Only chat copy that
end users see in normal conversation is localized here — operator-facing
logs, YAML docs, and power-user surfaces (/status internals) stay English.

Usage: ``i18n.t(bot_cfg, "welcome", name="Ben")``. Unknown keys fall back to
the key itself; missing translations fall back to English.
"""

from __future__ import annotations

_LANGS = ("en", "de")


def bot_language(bot_cfg: dict | None) -> str:
    raw = str((bot_cfg or {}).get("language", "en") or "en").strip().lower()
    return raw if raw in _LANGS else "en"


_STRINGS: dict[str, dict[str, str]] = {
    "welcome": {
        "en": (
            "👋 Hello {name}! I'm connected to Agent Zero.\n\n"
            "Send a message — text or voice — and I'll reply.\n\n"
            "🎙 /voice switches voice replies on or off.\n"
            "⚙️ /status shows the current modes.\n"
            "🗑 /clear resets this conversation. /help lists all commands."
        ),
        "de": (
            "👋 Hallo {name}! Ich bin mit Agent Zero verbunden.\n\n"
            "Schick mir eine Nachricht — Text oder Sprache — und ich antworte.\n\n"
            "🎙 /voice schaltet Sprachantworten ein oder aus.\n"
            "⚙️ /status zeigt die aktuellen Modi.\n"
            "🗑 /clear setzt diese Unterhaltung zurück. /help listet alle Befehle."
        ),
    },
    "continue_last": {
        "en": "▶️ Continue: {name}",
        "de": "▶️ Weiter: {name}",
    },
    "chat_cleared": {
        "en": "Chat cleared. Send a new message to start fresh.",
        "de": "Chat zurückgesetzt. Schick eine neue Nachricht, um frisch zu starten.",
    },
    "failed_create_session": {
        "en": "Failed to create chat session.",
        "de": "Chat-Session konnte nicht erstellt werden.",
    },
    "unauthorized": {
        "en": (
            "You are not authorized to use this bot.\n"
            "Your Telegram user ID is {user_id} — share it with the bot operator to request access."
        ),
        "de": (
            "Du bist für diesen Bot nicht freigeschaltet.\n"
            "Deine Telegram-User-ID ist {user_id} — gib sie dem Betreiber, um Zugriff zu erhalten."
        ),
    },
    "stt_empty": {
        "en": (
            "🎙 I couldn't understand that voice message (the transcription came "
            "back empty). Please try again or send it as text."
        ),
        "de": (
            "🎙 Ich konnte diese Sprachnachricht nicht verstehen (die Transkription "
            "war leer). Bitte versuch es nochmal oder schick sie als Text."
        ),
    },
    "stt_failed": {
        "en": (
            "🎙 I couldn't process that voice message right now. "
            "Please try again or send it as text."
        ),
        "de": (
            "🎙 Ich konnte diese Sprachnachricht gerade nicht verarbeiten. "
            "Bitte versuch es nochmal oder schick sie als Text."
        ),
    },
    "unsupported_type": {
        "en": (
            "🤷 I can't process this type of message yet. "
            "Please send text, voice, photos, videos, or files."
        ),
        "de": (
            "🤷 Diesen Nachrichtentyp kann ich noch nicht verarbeiten. "
            "Bitte schick Text, Sprache, Fotos, Videos oder Dateien."
        ),
    },
    "delivery_failed": {
        "en": (
            "⚠️ I finished, but the reply could not be delivered to Telegram. "
            "Send /retry to run your last message again."
        ),
        "de": (
            "⚠️ Ich bin fertig, aber die Antwort konnte nicht an Telegram "
            "zugestellt werden. Schick /retry, um deine letzte Nachricht erneut auszuführen."
        ),
    },
    "updates_paused": {
        "en": "⏳ Still working — live updates are paused by Telegram rate limits.",
        "de": "⏳ Ich arbeite noch — Live-Updates pausieren wegen Telegram-Rate-Limits.",
    },
    "voice_shortened": {
        "en": "🔊 Shortened for voice — the full reply is available as text.",
        "de": "🔊 Für Sprache gekürzt — die vollständige Antwort gibt es als Text.",
    },
    "voice_shortened_above": {
        "en": "🔊 Shortened for voice — the full reply is in the text above.",
        "de": "🔊 Für Sprache gekürzt — die vollständige Antwort steht im Text darüber.",
    },
    "edited_offer": {
        "en": "✏️ You edited your message.",
        "de": "✏️ Du hast deine Nachricht bearbeitet.",
    },
    "edited_offer_button": {
        "en": "🔁 Run again with the edited text",
        "de": "🔁 Mit dem neuen Text erneut ausführen",
    },
    "edited_gone": {
        "en": "Edit is no longer available.",
        "de": "Die Bearbeitung ist nicht mehr verfügbar.",
    },
    "edited_running": {
        "en": "Running with the edited text",
        "de": "Läuft mit dem neuen Text",
    },
    "busy_stop_first": {
        "en": "Agent is still working — use /stop first, then tap again.",
        "de": "Der Agent arbeitet noch — nutze zuerst /stop und tippe dann erneut.",
    },
    # Quick-action buttons under replies
    "btn_more": {"en": "⋯ More", "de": "⋯ Mehr"},
    "btn_show_text": {"en": "📝 Show text", "de": "📝 Text anzeigen"},
    "btn_shorter": {"en": "✂️ Shorter", "de": "✂️ Kürzer"},
    "btn_longer": {"en": "📏 Longer", "de": "📏 Ausführlicher"},
    "btn_to_voice": {"en": "🎙 To voice", "de": "🎙 Als Sprache"},
    "btn_back": {"en": "⬅ Back", "de": "⬅ Zurück"},
    "btn_copy_code": {"en": "📋 Copy code", "de": "📋 Code kopieren"},
    "btn_copy_command": {"en": "📋 Copy command", "de": "📋 Befehl kopieren"},
    "btn_on": {"en": "On", "de": "An"},
    "btn_off": {"en": "Off", "de": "Aus"},
    "btn_ux_on": {"en": "UX on", "de": "UX an"},
    "btn_ux_off": {"en": "UX off", "de": "UX aus"},
    "btn_ux_rich_on": {"en": "Rich on", "de": "Rich an"},
    "btn_ux_rich_off": {"en": "Rich off", "de": "Rich aus"},
    "btn_ux_drafts_on": {"en": "Drafts on", "de": "Drafts an"},
    "btn_ux_drafts_off": {"en": "Drafts off", "de": "Drafts aus"},
    "btn_ux_copy_on": {"en": "Copy on", "de": "Copy an"},
    "btn_ux_copy_off": {"en": "Copy off", "de": "Copy aus"},
    # /rich
    "rich_status": {
        "en": (
            "Rich messages: {state}.\n"
            "Native rendering for tables, headings, task lists and math. "
            "Tap a button or type /rich on|off for this session."
        ),
        "de": (
            "Rich-Nachrichten: {state}.\n"
            "Natives Rendering für Tabellen, Überschriften, Aufgabenlisten und Formeln. "
            "Tippe einen Button oder /rich on|off für diese Session."
        ),
    },
    "rich_on": {
        "en": (
            "Rich messages: on — tables, headings, task lists and math render "
            "natively in this session."
        ),
        "de": (
            "Rich-Nachrichten: an — Tabellen, Überschriften, Aufgabenlisten und "
            "Formeln werden in dieser Session nativ dargestellt."
        ),
    },
    "rich_off": {
        "en": "Rich messages: off — replies stay plain for easy copying.",
        "de": "Rich-Nachrichten: aus — Antworten bleiben unformatiert und gut kopierbar.",
    },
    "rich_usage": {
        "en": "Usage: /rich [on|off]",
        "de": "Verwendung: /rich [on|off]",
    },
    # /ux
    "ux_status": {
        "en": (
            "Enhanced Telegram UX:\n"
            "Rich messages: {rich}\n"
            "Native drafts: {drafts}\n"
            "Copy buttons: {copy}\n\n"
            "Tap a button or type /ux on|off, /ux rich on|off, "
            "/ux drafts on|off, or /ux copy on|off."
        ),
        "de": (
            "Erweiterte Telegram-UX:\n"
            "Rich-Nachrichten: {rich}\n"
            "Native Drafts: {drafts}\n"
            "Copy-Buttons: {copy}\n\n"
            "Tippe einen Button oder /ux on|off, /ux rich on|off, "
            "/ux drafts on|off oder /ux copy on|off."
        ),
    },
    "ux_all_on": {
        "en": "Enhanced Telegram UX: on — rich messages, native drafts, and copy buttons are active in this session.",
        "de": "Erweiterte Telegram-UX: an — Rich-Nachrichten, native Drafts und Copy-Buttons sind in dieser Session aktiv.",
    },
    "ux_all_off": {
        "en": "Enhanced Telegram UX: off — rich messages, native drafts, and copy buttons are disabled in this session.",
        "de": "Erweiterte Telegram-UX: aus — Rich-Nachrichten, native Drafts und Copy-Buttons sind in dieser Session deaktiviert.",
    },
    "native_drafts_on": {
        "en": "Native drafts: on — live response previews use Telegram drafts when supported.",
        "de": "Native Drafts: an — Live-Vorschauen nutzen Telegram-Drafts, wenn unterstützt.",
    },
    "native_drafts_off": {
        "en": "Native drafts: off — live response previews stay in the progress message.",
        "de": "Native Drafts: aus — Live-Vorschauen bleiben in der Fortschrittsnachricht.",
    },
    "copy_buttons_on": {
        "en": "Copy buttons: on — short code and command snippets get copy buttons.",
        "de": "Copy-Buttons: an — kurze Code- und Befehls-Snippets bekommen Kopierbuttons.",
    },
    "copy_buttons_off": {
        "en": "Copy buttons: off — replies keep the existing action buttons only.",
        "de": "Copy-Buttons: aus — Antworten behalten nur die bisherigen Aktionsbuttons.",
    },
    "ux_usage": {
        "en": "Usage: /ux [on|off] or /ux rich|drafts|copy [on|off]",
        "de": "Verwendung: /ux [on|off] oder /ux rich|drafts|copy [on|off]",
    },
    "actions_on": {
        "en": "Reply actions: on — the More menu will be shown for this session.",
        "de": "Antwort-Aktionen: an — das Mehr-Menü wird in dieser Session angezeigt.",
    },
    "actions_off": {
        "en": "Reply actions: off — the More menu is hidden for this session.",
        "de": "Antwort-Aktionen: aus — das Mehr-Menü ist in dieser Session ausgeblendet.",
    },
    "actions_usage": {
        "en": "Usage: /actions [on|off]",
        "de": "Verwendung: /actions [on|off]",
    },
    "suggest_status": {
        "en": (
            "Suggested replies: {state}.\n"
            "Shows up to three tap-to-send follow-up suggestions under replies. "
            "Tap a button or type /suggest on|off for this session."
        ),
        "de": (
            "Antwortvorschläge: {state}.\n"
            "Zeigt bis zu drei antippbare Folgevorschläge unter Antworten. "
            "Tippe einen Button oder /suggest on|off für diese Session."
        ),
    },
    "suggest_on": {
        "en": "Suggested replies: on — follow-up suggestions appear under replies in this session.",
        "de": "Antwortvorschläge: an — Folgevorschläge erscheinen in dieser Session unter den Antworten.",
    },
    "suggest_off": {
        "en": "Suggested replies: off — no follow-up suggestions in this session.",
        "de": "Antwortvorschläge: aus — keine Folgevorschläge in dieser Session.",
    },
    "suggest_usage": {
        "en": "Usage: /suggest [on|off]",
        "de": "Verwendung: /suggest [on|off]",
    },
    "suggest_gone": {
        "en": "Suggestion is no longer available.",
        "de": "Der Vorschlag ist nicht mehr verfügbar.",
    },
    "queued_notice": {
        "en": "📥 Queued — I'll get to it right after the current task.",
        "de": "📥 Eingereiht — ich kümmere mich direkt nach der aktuellen Aufgabe darum.",
    },
    "help_intro": {
        "en": "Reply and voice modes apply to this chat and switch anytime with the commands below.",
        "de": "Antwort- und Sprachmodi gelten für diesen Chat und lassen sich jederzeit mit den Befehlen unten umschalten.",
    },
}


def t(bot_cfg: dict | None, key: str, **fmt) -> str:
    """Translated string for the bot's configured language, formatted with fmt."""
    lang = bot_language(bot_cfg)
    entry = _STRINGS.get(key) or {}
    template = entry.get(lang) or entry.get("en") or key
    if not fmt:
        return template
    try:
        return template.format(**fmt)
    except Exception:
        return template
