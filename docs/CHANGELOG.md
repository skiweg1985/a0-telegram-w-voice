# Changelog

Older entries are chronological release history and may mention commands/features that were later removed. For current operator documentation, use `README.md` plus the latest `[Unreleased]` notes.

## [Unreleased]

### Added

- **Enhanced Telegram UX** (`/ux`): macro command for rich final replies, native plain-text draft previews, and copy buttons. New WebUI bots default these on; existing bots keep conservative missing-key defaults until enabled. Copy buttons are limited to short code/command snippets and merge ahead of suggested-reply chips.
- **Suggested replies** (`/suggest [on|off]`, bot default `suggested_replies_enabled`, WebUI toggle): after each text reply the utility LLM proposes up to three tap-to-send follow-up chips (💬), generated *after* delivery so the answer is never delayed, token-guarded like the other reply actions, localized via the conversation language, and cleared on the next reply and `/clear`.
- **Message queue** (`queue_messages`, default on): button-driven follow-ups (Retry, Shorter/Longer, suggestions, edited re-runs, Continue) that arrive while the agent is busy are queued with a "📥 Queued" notice instead of being rejected; multiple queued turns are merged and dispatched automatically once the current run finishes (chain end).

- New `/rich [on|off]` command: per-session toggle for native rich-message rendering (tables, headings, task lists, math) with inline buttons; the WebUI/YAML `rich_messages.enabled` becomes the default for new sessions, shown in `/status`, reset on `/clear`/`/newchat`. The session override also gates the rich system-prompt guidance so the agent only produces rich structures that will render.
- Settings keyboards (`/voice`, `/detail`, `/detail_before`, `/optimize_output`, `/actions`, `/rich`) now edit the tapped message in place and mark the active option with a checkmark, instead of stacking confirmation bubbles below stale keyboards.
- Incoming **GIFs/animations** are downloaded and labeled for the agent; unsupported message types (polls, dice, stories, …) answer with a short "can't process this type" notice in private chats instead of silently forwarding an empty turn (groups drop them silently).
- **Emoji-reaction acknowledgements** (`reactions_enabled`, default on): 👀 on receipt, 👍 on delivered reply, 😢 on delivery failure; quiet no-op on old Bot API versions. **Edited messages** get a ✍️ reaction plus a one-tap "Run again with the edited text" offer (private chats).
- **Session UX**: one-line previews (last user request) in the `/session` picker, 📌 pin/unpin from the details view (pinned sessions sort first), and a "▶️ Continue last session" button on `/start`.
- **i18n layer** (`language: en|de`, WebUI selector): welcome, confirmations, notices, quick-action buttons, `/help`, and a German Telegram command menu via `setMyCommands(language_code="de")`. Operator surfaces (`/status` internals, session picker labels) stay English for now.

- Voice replies that exceed the TTS character cap are now cut at a sentence boundary instead of mid-word, carry a "🔊 Shortened for voice" caption, and force the **Show text** reveal button so the full reply stays reachable (also applies to the **To voice** quick action). The default `speech.reply.max_chars` was raised from 700 to 1400.
- STT failures now answer the user directly ("I couldn't understand that voice message…", reusing the progress bubble when possible) instead of injecting a raw `[Voice transcript failed: …]` marker into the agent prompt.
- When the final reply cannot be delivered after all retries, the chat now shows "⚠️ … Send /retry" (the leftover progress bubble is edited into the notice) instead of freezing on "In progress…" while the failure was only logged server-side.

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
- Response transform quick actions on text replies: **Shorter** and **Longer** rewrite the last assistant answer in place (no more `More technical` / `Step by step`).
- New `/shortcut` slash command works on the active session. With no argument it shows inline buttons; sub-commands/buttons: `shorter` / `longer` (re-trigger the transforms) and `summary` (utility-LLM summary delivered as a separate Telegram message).
- `/session` picker details view now shows a fresh utility-LLM-generated 📝 Summary block instead of the old single-line "Topic" extract.
- `/session` picker gained a **🗑 Delete** action: open a session's details and tap Delete to permanently remove the on-disk chat file. Deleting the active session automatically starts a fresh new chat. Deletion is **button-driven** (no text command) and applies to bound sessions plus unbound web sessions whose `CTX_TG_USER_ID` matches the current Telegram user; one confirmation step before the file is removed.
- WebUI + YAML opt-in for Telegram Bot API rich final replies (`rich_messages.enabled`) with a separate reserved switch for rich draft previews (`rich_messages.drafts_enabled`). Defaults stay off for client compatibility and copyability.
- When rich final replies are enabled, Telegram system prompts now let the agent use tables, task lists, short headings, details, and math when they improve readability.
- Rich-message prompt guidance now documents the confirmed Telegram syntax for headings, text formatting, links, blockquotes, ordered/unordered/task lists, aligned tables, fenced code blocks, math, and collapsible `<details>` sections.
- Opt-in `/reload` command for Telegram bot admins. It requires `allow_restart_command: true`, a matching `admin_users` entry, and an inline Approve/Cancel confirmation before Agent Zero reloads.
- `/reload` now leaves a short-lived restart marker and sends a one-time styled Telegram confirmation to the approving chat after the bot reconnects.

### Removed

- WebUI no longer exposes Progress Message Editing toggles. Progress edits, live reply previews, final in-place edits, and native draft fallback now run automatically; operator tuning remains YAML-only.
- `/speakstyle` command removed. Use `/optimize_output voice` for a voice-oriented answer style and `/optimize_output off` to turn it off.
- `/alsotext` command removed. Control text alongside voice via `/voice voice_text` (voice + text) or `/voice voice_only` (voice without text), or set the bot's default **Voice Reply Mode**. Any leftover session override is cleared on `/clear`.
- Legacy `/tts` session fallback (`telegram_tts_voice_session`) removed. The old TTS inline control is gone; use `/voice`.

### Fixed

- **`/start` and `/clear` crashed with a `NameError`** (`reply_markup` was referenced but never defined), so new users got no welcome message and `/clear` never confirmed the reset.
- Long messages are now split HTML-tag-aware at the 4096-char limit: tags left open at a chunk boundary are closed and re-opened in the next chunk, so a `<pre>` code block or `<b>` span crossing the limit no longer loses its formatting via the plain-text parse-error fallback. That fallback also decodes HTML entities now, so users see `<` instead of a literal `&lt;`.
- Tool-status lines no longer show a `✓` checkmark the moment a tool **starts**; running steps render with `⏳` and switch to `✓` when the completion detail replaces the line.
- **Chat stuck on "🤔 Drafting reply…"**: Background progress edits (live preview, phase changes, tool detail lines) raced the final reply. A queued or in-flight status edit could land after the final edit and overwrite the delivered answer with "Drafting reply…", or re-create a status bubble after cleanup that nothing ever removed — the answer was visible in the web UI but the Telegram chat looked frozen. Progress updates are now fenced by an epoch counter and drained (`_finalize_progress_updates`) before the final send/edit, so the final message is always the last write.
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
