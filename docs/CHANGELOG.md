# Changelog

## [Unreleased]

### Added

- `/newchat` — start a fresh AgentContext for the same Telegram chat; the previous conversation stays in the Agent Zero browser UI as a separate chat entry. `/clear` still resets history within the same context.
- New contexts created via Telegram are now immediately persisted (`save_tmp_chat`), so they appear in the browser UI right after `/start` or the first message — no longer delayed until the first agent reply.
- `/optimize_output` with no argument: inline keyboard (Voice / Text / Off / Reset) in addition to typed args.
- `/model` with no argument: when per-chat override is allowed and presets exist, inline buttons to pick a preset by index (list changes → send `/model` again).
- `/tts` with no argument: session voice summary + inline keyboard (Default / Muted / Auto / Force).
- `/project` with no argument: when projects exist, inline buttons by index (list changes → send `/project` again).

### Changed

- `/clear` now persists the reset state immediately (`save_tmp_chat`) so the browser UI reflects the cleared history without delay.
- `/tts` with no argument no longer toggles mute; use the **Muted** or **Default** button (or `/tts off` / `/tts on`).
- `handle_callback_query`: callbacks with prefix `tgx|` are handled locally (plugin UI); other `callback_data` still goes to the agent as before.
- `/status` reply: section icons (model, utility, history, TTS/STT, …), bold labels via HTML, monospace for IDs/models, clearer run/pause line; dynamic values HTML-escaped.

## [0.10.3] - 2026-03-29

### Fixed

- Job loop no longer hard-imports `handle_optimize_output`: if `handler.py` is an older copy (mixed deploy), the bot starts and logs a warning; `/optimize_output` and `/speakstyle` are omitted until all plugin files match.

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
