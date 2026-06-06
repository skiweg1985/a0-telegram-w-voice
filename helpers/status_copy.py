"""Centralized user-facing Telegram status copy."""

from __future__ import annotations


def _normalize_phase(phase: str | None) -> str:
    return str(phase or "").strip().lower()


def progress_title(phase: str | None = None, *, done: bool = False) -> str:
    if done:
        return "✅ Done"
    return {
        "stt": "🎤 Transcribing voice…",
        "gen": "🤔 Drafting reply…",
        "tts": "🔊 Creating voice reply…",
    }.get(_normalize_phase(phase), "⏳ Working on it…")


def progress_hint() -> str:
    return "Still working…"


def activity_label(phase: str | None) -> str:
    return {
        "stt": "transcribing voice",
        "gen": "drafting reply",
        "tts": "creating voice reply",
    }.get(_normalize_phase(phase), "")


def completion_title(
    *,
    sent_text: bool = False,
    sent_voice: bool = False,
    sent_artifact_count: int = 0,
) -> str:
    if sent_artifact_count > 0 and not sent_text:
        if sent_artifact_count == 1:
            return "📎 Sent attachment"
        return f"📎 Sent {sent_artifact_count} attachments"
    if sent_voice and not sent_text:
        return "🎙 Voice reply sent"
    return "✅ Done"
