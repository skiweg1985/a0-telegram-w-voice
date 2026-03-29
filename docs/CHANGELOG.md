# Changelog

## [Unreleased]

## [0.10.1] - 2026-03-29

### Changed

- `register_bot_command_menu` moved to `helpers/command_registry.py`; job loop imports it from there (avoids ImportError if an older `bot_manager.py` was deployed without that symbol).

## [0.10.0] - 2026-03-29

### Added

- Telegram slash commands: `/help`, `/status`, `/tts`, `/compact`, `/stop`, `/project`, `/model`, `/pause`, `/resume` (existing `/start`, `/clear`).
- Command menu registration via `set_my_commands` on bot start (`helpers/command_registry.py`).
- Per-session `/tts` override (`telegram_tts_voice_session` in context data, persisted in chat); cleared on `/clear`.
