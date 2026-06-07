# Changelog

## [Unreleased]

### Added

- `/retry` re-runs your last message, and `/undo` drops the last exchange (your message and the agent's reply) from the session history.
- `/topic [name]` opens a named conversation thread in the same chat, or starts a new one; without a name it lists existing topics.
- Session search is now button-driven: tapping **Search** in the session picker prompts for a term via Telegram's reply box and uses your next message to filter, instead of only showing help text.
- Unauthorized users now get a clear, throttled reply with their Telegram user ID so they can request access, instead of silence.
- Visible "still working" notice when live progress edits are repeatedly paused by Telegram rate limits, so a stalled progress message no longer looks frozen. The typing indicator is also refreshed after each new progress message.
- WebUI: per-bot defaults for **Answer Style** (`optimize_output_default`) and **Tool Status Detail** (`telegram_detail_level`), plus a **Walkie-talkie preset** button. Chat-overridable settings are labeled as defaults for new sessions with the matching slash command.
- Emoji icons and human-readable labels for `/detail info` and `/detail debug` steps (e.g. memory tools show a brain icon, code execution a laptop). Icons are resolved by exact match, prefix-before-colon, then prefix rules with a built-in map and configurable overrides.
- New bot config keys: `telegram_detail_icons_enabled` (default true), `telegram_detail_tool_icons` (override map), `telegram_detail_max_body_chars` (debug JSON truncation limit, default 3200).
- New tool-start status mode: `/detail_before [on|off]` toggles execute-before tool updates per session with inline buttons, and bot config `telegram_detail_execute_before` sets the default for new sessions.
- New `/detail smart` mode: tool steps are summarized with the configured utility model from redacted tool args, giving more context than `info` without exposing full verbose payloads.
- Progress messages that exceed Telegram's 4096-char limit are now truncated at a safe boundary before sending, preventing API errors from oversized debug payloads.
- New Telegram progress config keys `live_response_preview_interval_ms` and `live_response_preview_buffer_threshold` to tune live-preview cadence and early flush behavior.
- Response transform quick actions on text replies: **Shorter**, **More technical**, and **Step by step** rewrite the last assistant answer in place instead of continuing the task.

### Removed

- WebUI no longer exposes Progress Message Editing toggles. Progress edits, live reply previews, final in-place edits, and native draft fallback now run automatically; operator tuning remains YAML-only.
- `/speakstyle` command removed. Use `/optimize_output voice` for a voice-oriented answer style and `/optimize_output off` to turn it off.
- `/alsotext` command removed. Control text alongside voice via `/voice voice_text` (voice + text) or `/voice voice_only` (voice without text), or set the bot's default **Voice Reply Mode**. Any leftover session override is cleared on `/clear`.
- Legacy `/tts` session fallback (`telegram_tts_voice_session`) removed. The old TTS inline control is gone; use `/voice`.

### Fixed

- **Voice-only "Show text" after restart**: The reveal button's text and token are now persisted with the chat (keys without leading underscore) and the context is saved after each reply, so tapping "Text anzeigen" still works after a bot restart or context reload instead of returning "Text is no longer available". `/clear` drops the stored reveal text/token.
- **Voice-only replies**: In `voice_only` mode the "Show text" quick action no longer triggers a visible text bubble. The reveal button is now attached directly to the voice message (`sendVoice` inline keyboard), and the text is only sent after the user taps it. Text is still sent as a fallback when voice delivery fails.
- **`also_send_text`**: If the model only fills `voice_text` (TTS) and leaves `text` empty, Telegram now still sends a text bubble when **Also send text** is enabled (uses `voice_text` as fallback). Config value `also_send_text` is parsed robustly (strings like `"false"` no longer behave like Python `bool("false") == True`).
- `/detail` progress updates: step HTML from `format_step_html` is no longer run through `md_to_telegram_html`, so Telegram renders bold/code/blockquote correctly instead of showing literal tags and `&quot;` entities.
- Execute-before tool status updates no longer suppress the normal completion-time detail line when the start update was skipped due to throttling.

### Changed

- Private-chat reply keyboard stays attached on slash-command and inline-picker replies (`/retry`, `/undo`, session callbacks, and similar), so the DM control pad no longer disappears after status messages.
- Single-photo/video/document replies can carry the agent text as a media caption instead of a separate bubble; inline keyboards attach to the media when that reads better. Multi-item albums use a short companion message for keyboard-only replies.
- Telegram response prompt guidance now distinguishes attachments vs `telegram_items`, recommends direct multi-file sends over zipping when appropriate, and documents caption/keyboard patterns for media replies.
- Slash-command modes are now switch-only: `/detail` and `/optimize_output` no longer offer **Reset**/`reset`/`default`. Every command sets a concrete mode (e.g. `/detail off`), and the WebUI default applies again after `/newchat` or `/clear`.
- `/voice off` copy now reads "Voice mode: off — replies are text only" instead of implying a return to a configured default.
- `/start` welcomes with the voice and status commands; `/help` notes that reply and voice modes can be switched anytime in chat.
- `/status` Reply line now also shows `tool start on|off`, and `/detail_before` participates in the same inline mode-switch UX as `/detail`.
- The voice-only reveal button label is now "Show text" (was the German "Text anzeigen") so Telegram copy is consistently English.
- The agent is guided to confirm risky actions with an Approve/Cancel inline keyboard and to offer choices as inline buttons; button taps are fed back into the agent automatically.
- Voice reply controls consolidated into a single `/voice` command. `/voice` now supports `auto` (voice reply only when the incoming message was a voice message), alongside `voice_only`, `voice_text`, `text_only`, and `off`. The inline keyboard gained an **Auto** button.
- WebUI: the bot config now exposes a single **Voice Reply Mode** dropdown (off, auto, voice_only, voice_text, text_only) that mirrors `/voice`, replacing the former mode selector plus separate "Also send text" toggle. Configs that still use `voice_mode: force` together with `also_send_text` keep working unchanged.
- WebUI no longer shows operator-only tuning keys (detail throttling, labels and icons, progress edit throttle and live-preview character cap, STT/TTS endpoint overrides, STT language hint, request timeouts). These stay configurable in `default_config.yaml` and are preserved across WebUI edits.
- Default `telegram_detail_level` is now `info` instead of `off`: new chats and bots without an explicit value show throttled tool-step lines. An explicitly configured `off` is still respected; set `telegram_detail_level: off` or use `/detail off` to silence steps.
- Telegram progress bubble title: `🧠 Working…` → `🔄 In progress…` (covers thinking, tool steps, and live draft preview).
- `/status` Reply line: removed redundant `chat` extras that echoed session overrides already shown in the effective values (`shaping`, `tool detail`). The line now reads `⚙️ Reply: shaping <mode> · tool detail <level>` — clean, no meta info.
- `/status`: Voice line shows effective reply mode (`replies`) instead of `voice default`; Reply line uses `chat` instead of `overrides`, with concise extras. Tool detail is labeled **verbose** when the internal level is `debug`.
- `/detail`: user-facing name **verbose** for the highest level (config value and slash `debug` still work); inline button **Verbose**.
- `/optimize_output` (no argument): status text without “plugin default” / `session=` meta.
- `speech.effective_voice_reply_mode()` and `detail_status.detail_level_display()` for consistent effective/display values.
- Telegram live response previews now use a background coalescing worker so streamed chunks never block agent output and preview edits are flushed on cadence or buffer growth.
- Tool detail status updates now prefer scheduled background progress edits instead of waiting synchronously on each step.

- `/status`: flat one-line-per-topic layout (OpenClaw-style scan pattern); header with bot name; order Activity → models → context → voice → reply → project → session; combined reply chat extras; friendlier `unknown` / `other (custom)` model fields.
- `/detail info` no longer shows a bare `Step: tool_name` line; it now displays an emoji prefix followed by the configured label (same visual treatment as debug, minus the JSON block).

### Added (previous)

- `/newchat` — start a fresh AgentContext for the same Telegram chat; the previous conversation stays in the Agent Zero browser UI as a separate chat entry. `/clear` still resets history within the same context.
- New contexts created via Telegram are now immediately persisted (`save_tmp_chat`), so they appear in the browser UI right after `/start` or the first message — no longer delayed until the first agent reply.
- `/optimize_output` with no argument: inline keyboard (Voice / Text / Off / Reset) in addition to typed args.
- `/model` with no argument: when per-chat override is allowed and presets exist, inline buttons to pick a preset by index (list changes → send `/model` again).
- `/tts` with no argument: session voice summary + inline keyboard (Default / Muted / Auto / Force).
- `/project` with no argument: when projects exist, inline buttons by index (list changes → send `/project` again).

### Changed

- `response.break_loop` parsing is now tolerant (`false`, `0`, `off`, etc.) so inline progress updates trigger more reliably instead of being skipped when providers serialize booleans as strings.
- `/detail debug` now shows full tool step information (full tool name + complete args payload) instead of the compact one-line step label.
- `/clear` now persists the reset state immediately (`save_tmp_chat`) so the browser UI reflects the cleared history without delay.
- `/tts` with no argument no longer toggles mute; use the **Muted** or **Default** button (or `/tts off` / `/tts on`).
- `handle_callback_query`: callbacks with prefix `tgx|` are handled locally (plugin UI); other `callback_data` still goes to the agent as before.
- `/status` reply: section icons (model, utility, history, TTS/STT, …), bold labels via HTML, monospace for IDs/models, clearer run/pause line; dynamic values HTML-escaped.
- `/status` layout: grouped blocks (Models, Tokens &amp; history, Project, Voice, Reply options, Activity, Session ID) with blank lines between sections; one line per metric where possible; clearer labels (e.g. tool-step lines, output shaping, override bullets).
- Tool detail status lines (`/detail info|debug`) now go through progress message editing, so the chat can update one message in place instead of posting a new line per step.

## [0.11.3] - 2026-03-30

### Added

- New slash command `/alsotext [on|off|reset]` with inline buttons to toggle `also_send_text` per chat session without editing YAML.

### Changed

- `optimize_output` now supports `auto` (`/optimize_output auto` and config default), which resolves per turn to `voice` or `text` based on effective voice-reply behavior (`force` always voice; `auto` follows last input type).
- Telegram system-prompt shaping is now dynamic: voice/text optimize snippets receive the resolved `also_send_text` status, so the model can intentionally separate `text` (readable) and `voice_text` (speakable summary).
- `/status` Reply line now includes effective `also text` (`on`/`off`) in addition to shaping and tool-detail mode.
- When sending replies, `also_send_text` now uses effective session-aware behavior (config plus `/alsotext` override), not only static YAML.

## [0.11.2] - 2026-03-30

### Fixed

- **Plugin external config vs. existing Telegram chats**: `telegram_bot_cfg` on the agent context was only set when the chat was first created, so changes under Plugin settings (STT/TTS URLs, `voice_mode` defaults, progress, detail defaults, etc.) had no effect until `/newchat` or a new user. Existing sessions now refresh the stored bot config on every message or callback so UI changes apply without losing the conversation.

## [0.11.1] - 2026-03-30

### Fixed

- **Voice reply mode (de-escalation only)**: The agent's per-response `voice_mode` can only *lower* the effective mode (e.g. `voice_mode: "off"` for a code-heavy reply), never escalate above config/session. The deprecated `voice: true/false` response parameter is ignored; the Telegram system prompt documents `voice_mode: "off"` only.

## [0.10.4] - 2026-03-29

### Added

- `/detail` — tool-run status in chat: `off` (default, final answer only), `info` (throttled “Step: …” lines), `debug` (more frequent, still throttled). No argument shows current level plus inline buttons; `reset` clears the session override. Bot keys: `telegram_detail_level`, `telegram_detail_*_min_interval_sec`, optional `telegram_detail_exclude_tools` / `telegram_detail_tool_labels`. Status lines never include tool arguments.

### Changed

- `/status` includes **Tool detail** (effective level and session override).
- `/clear` also clears the `/detail` session override and detail throttle state.

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
