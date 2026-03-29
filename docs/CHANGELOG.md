# Changelog

## [Unreleased]

## [0.10.2] - 2026-03-29

### Added

- `/optimize_output voice|text|off|reset` — per-session system-prompt hint for TTS-friendly vs Telegram-readable answers; no argument prints current mode. Shown on `/status`.
- `/speakstyle` — shortcut for voice-oriented optimize (same handler); `/speakstyle off` disables the extra snippet.
- `speech.reply.optimize_output_default` in bot config (`off` \| `voice` \| `text`); applied for new Telegram contexts until the user changes the session.
- Optional `voice_text` on the `response` tool: when set, TTS uses it instead of `text` (chat message still uses `text`).
- Prompts `fw.telegram.optimize_output_voice.md` and `fw.telegram.optimize_output_text.md`.

## [0.10.1] - 2026-03-29

### Changed

- `register_bot_command_menu` moved to `helpers/command_registry.py`; job loop imports it from there (avoids ImportError if an older `bot_manager.py` was deployed without that symbol).

## [0.10.0] - 2026-03-29

### Added

- Telegram slash commands: `/help`, `/status`, `/tts`, `/compact`, `/stop`, `/project`, `/model`, `/pause`, `/resume` (existing `/start`, `/clear`).
- Command menu registration via `set_my_commands` on bot start (`helpers/command_registry.py`).
- Per-session `/tts` override (`telegram_tts_voice_session` in context data, persisted in chat); cleared on `/clear`.
