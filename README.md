# a0-telegram-w-voice

![version](https://img.shields.io/badge/version-0.11.3-blue)

Agent Zero plugin: **Telegram** with optional **STT/TTS** (voice in, voice out), live response preview, inline buttons, and background progress streaming. Aligned with the upstream conventions in [a0-create-plugin](https://github.com/agent0ai/agent-zero/blob/main/skills/a0-create-plugin/SKILL.md).

**Canonical repository:** [https://github.com/skiweg1985/a0-telegram-w-voice](https://github.com/skiweg1985/a0-telegram-w-voice)

**Plugin ID:** `telegram_integration_voice` (folder name under `usr/plugins/` must match `plugin.yaml` `name`). The GitHub repo name (`a0-telegram-w-voice`) differs; always use the folder name `telegram_integration_voice` when installing.

## Install (Git, recommended)

1. **Disable or remove** the core Telegram plugin (`_telegram_integration`) so only one Telegram integration is active.

2. Clone into the correct plugin directory (folder name must be `telegram_integration_voice`):

   ```bash
   git clone https://github.com/skiweg1985/a0-telegram-w-voice.git telegram_integration_voice
   ```

   Move or place `telegram_integration_voice/` under your Agent Zero tree as `usr/plugins/telegram_integration_voice/` (so `usr/plugins/telegram_integration_voice/plugin.yaml` exists).

3. On first install, Agent Zero runs `hooks.py` `install()` which installs `requirements.txt` into the framework Python environment. You can also run **`execute.py`** from the Plugins UI (or `python execute.py` in that folder) if you need to reinstall dependencies manually. If `aiogram` is missing, the plugin can still attempt a runtime install when a bot is enabled.

4. Enable **Telegram Integration (Voice)** under Plugin settings (External) and configure bots.

### Install via Agent Zero API (`install_git`)

The installer must target the plugin folder name `telegram_integration_voice`, not the repo name. Pass **`plugin_name`**:

```json
{
  "action": "install_git",
  "git_url": "https://github.com/skiweg1985/a0-telegram-w-voice.git",
  "plugin_name": "telegram_integration_voice"
}
```

Use the authenticated HTTP API as described in [a0-manage-plugin](https://github.com/agent0ai/agent-zero/blob/main/skills/a0-manage-plugin/SKILL.md) (CSRF session, `POST` to the plugin installer endpoint).

## Install (copy without Git)

Copy this repository contents (the plugin root with `plugin.yaml`, `api/`, `helpers/`, etc.) into:

`usr/plugins/telegram_integration_voice/`

Then run **`execute.py`** from the Plugins UI if dependencies are not yet installed. Updates are easier if you use a Git clone instead.

## Update

If the plugin directory is a Git clone:

```bash
cd /path/to/usr/plugins/telegram_integration_voice
git pull origin main
```

(Use your default branch if it is not `main`.) Agent Zero may run `pre_update()` then pull, then `install()` again so dependencies stay in sync.

Refresh the plugin cache: toggle the plugin off and on in the Plugins UI, or restart the Agent Zero process/container. See [a0-manage-plugin — Update a Plugin](https://github.com/agent0ai/agent-zero/blob/main/skills/a0-manage-plugin/SKILL.md).

## Features

### Voice (STT / TTS)

- **Speech-to-text** for incoming Telegram voice and audio messages.
- **Text-to-speech** for outgoing replies — delivered as Telegram voice bubbles.
- Providers: OpenAI-compatible APIs (incl. LiteLLM), ElevenLabs, custom HTTP endpoints, optional local engines.
- Raw PCM output (e.g. Gemini-compatible endpoints, `format: pcm`) is automatically converted to `ogg/opus` before sending; `ffmpeg` used when available.
- `/voice` controls the reply mode per session: `auto` (speak only after a voice message), `voice_only`, `voice_text` (voice + text), `text_only`, `off`.
- **Voice-only "Show text"**: in `voice_only` mode an inline button is attached to the voice message — tapping it reveals the text reply on demand without a separate bubble. Persisted across restarts; cleared on `/clear`.
- **Output shaping** via `/optimize_output` (`voice`, `text`, `off`) — steers how the agent phrases replies for the active session.

### Live Response Preview

Streamed agent responses appear as a **live-edited Telegram message** while the agent is still typing — similar to the native draft preview in other chat apps.

- A **background coalescing worker** collects stream chunks and flushes them on a configurable cadence, so agent output is never blocked by Telegram I/O.
- **Flood-control safe**: if Telegram rate-limits a progress edit (HTTP 429), the update is silently skipped rather than falling back to a new message. The final answer always lands correctly.
- Tunable via `progress:` config keys: `live_response_preview_interval_ms`, `live_response_preview_buffer_threshold`, `live_response_preview_chars`.

### Tool Status & Detail Level

- `/detail` controls what appears in chat while tools are running: `off` (final answer only), `info` (throttled step lines), `smart` (utility-model summary), `verbose` (full tool detail).
- `/detail_before` controls whether a tool-status line is already shown when a tool **starts**: `on` (default) or `off` for the current session.
- Each step shows an **emoji icon and a human-readable label** (e.g. 🧠 for memory tools, 💻 for code execution). Icons and labels are configurable per tool.
- Detail updates are sent as **in-place progress edits** — a single bubble is updated rather than a new message per step.
- When `/detail_before on` is active, the same progress bubble shows the step at tool start and then replaces that line with the completion-time outcome.
- Long debug payloads are truncated at a safe boundary before sending (`telegram_detail_max_body_chars`).

### Slash Commands & Inline Buttons

- **Inline keyboards** on mode-switching commands: `/detail`, `/detail_before`, `/voice`, `/optimize_output`, `/project`, `/model`, and `/shortcut` (no argument) — tap to switch or run shortcuts without typing.
- `/title` sets a manual title for the current session, or `/title auto` returns to automatic naming.
- `/actions` toggles the per-reply **More** menu for the current session. The More menu offers `Shorter`, `Longer`, `To voice`, and `Back`; voice-only replies can also show `Show text`.
- **Approve / Cancel flows**: the agent can present risky actions as inline keyboard choices; taps are fed back into the agent automatically.
- **Unauthorized users** receive a clear, throttled reply with their Telegram user ID so they can request access.
- **`/session` picker**: paginated list of saved sessions with inline navigation, details view (with a 📝 Summary block of the most recent turns), **button-driven search** (tap Search, send a term, results filter inline) and a **🗑 Delete** action that removes the on-disk chat file (a fresh new session is started automatically when deleting the active one).
- `/retry` re-runs your last message; `/undo` drops the last exchange (your message and the agent's reply) from session history.
- `/topic [name]` opens a named conversation thread in the same chat, or lists existing topics without a name.

### WebUI

- Per-bot defaults for **Answer Style** (`optimize_output_default`) and **Tool Status Detail** (`telegram_detail_level`) directly in the plugin settings UI.
- The WebUI exposes **Off**, **Info**, **Smart**, and **Verbose** for the default tool-detail level.
- **Walkie-talkie preset** button for quick voice-oriented configuration.
- **Quick action buttons** can be enabled/disabled in the WebUI. This controls the per-reply **More** menu (`Shorter`, `Longer`, `To voice`, `Back`) and the voice-only **Show text** button.
- **Update from Git** and **Test Connection** actions are available in the WebUI for Git-based installs and token checks.
- Operator-only tuning (detail throttling, icon overrides, progress timing, STT/TTS endpoint details) is YAML-only — no visual clutter in the UI.

---

## Slash commands (summary)

| Command | Purpose |
|---------|---------|
| `/help` | List commands |
| `/start` | Welcome; ensures session |
| `/status` | Model, tokens, project, TTS/STT, run state |
| `/clear` | Reset conversation history (same context) |
| `/newchat` | New session; old chat stays in browser UI |
| `/session` | Paginated session picker; `/session search <term>` to filter, open a session and tap **🗑 Delete** to remove it (active session triggers a fresh new chat) |
| `/title` | Set a manual session title, or `/title auto` to restore automatic naming |
| `/actions` | Toggle the per-reply **More** menu for this session |
| `/detail` | `off` / `info` / `smart` / `verbose`, or no arg shows level + **inline buttons** |
| `/detail_before` | `on` / `off`, or no arg shows current tool-start mode + **inline buttons** |
| `/voice` | `voice_only` / `voice_text` / `auto` / `text_only` / `off`, or no arg shows mode + **inline buttons** |
| `/optimize_output` | `voice` / `text` / `off`, or no arg shows current mode **with inline buttons** |
| `/retry` | Re-run your last message |
| `/undo` | Drop the last exchange from session history |
| `/topic` | Start or list named conversation threads |
| `/compact` | Compress history (utility LLM) |
| `/shortcut` | No arg shows inline buttons; `shorter` / `longer` rewrite the last answer; `summary` delivers a utility-LLM session summary as a separate message |
| `/stop` | Abort running task |
| `/project` | Active + available projects + **buttons**; or `/project <name>` |
| `/model` | Show current model + **preset buttons**; or `/model <preset>` |
| `/pause` / `/resume` | Pause or resume agent loop |

---

## Configuration example

```yaml
bots:
  - name: my_bot
    enabled: true
    token: "<telegram-bot-token>"
    mode: polling
    allowed_users: ["123456789"]

    telegram_detail_level: info                 # off | info | smart | debug (verbose alias in chat)
    telegram_detail_execute_before: true        # default; set false to hide tool-start lines and only show completion-time detail
    telegram_detail_info_min_interval_sec: 5
    telegram_detail_debug_min_interval_sec: 1.5
    telegram_detail_icons_enabled: true          # emoji prefix per step
    # telegram_detail_tool_icons: {}             # override icons, e.g. { "memory_load": "\U0001f4cc" }
    # telegram_detail_max_body_chars: 3200       # verbose JSON truncation limit

    rich_messages:
      enabled: false        # opt-in native final replies for tables/task lists/headings/details/math
      drafts_enabled: false # separate opt-in switch reserved for rich live previews

    progress:
      edit_throttle_ms: 200
      completed_mode: delete                     # delete | none | edit; avoids leftover "Completed" bubbles
      live_response_preview_interval_ms: 800     # max cadence for live draft preview edits
      live_response_preview_buffer_threshold: 24 # flush early after enough buffered chars
      live_response_preview_chars: 1200          # visible draft text cap

    speech:
      stt:
        enabled: true
        provider: openai_compatible
        base_url: "http://litellm.example.local:4000/v1"
        api_key: "${LITELLM_API_KEY}"
        model: "whisper-1"
        language: "de"
        timeout_sec: 60

      tts:
        enabled: true
        provider: openai_compatible
        base_url: "http://litellm.example.local:4000/v1"
        api_key: "${LITELLM_API_KEY}"
        model: "gpt-4o-mini-tts"
        voice: "alloy"
        format: "opus"
        timeout_sec: 60

      reply:
        optimize_output_default: off   # off | voice | text | auto — new sessions; /optimize_output overrides
        voice_mode: auto               # off | auto | voice_only | voice_text | text_only
        max_chars: 700
        quick_actions:
          enabled: true                # default for the per-reply More menu; /actions overrides per session
          show_text: true              # in voice-only replies, allow revealing the text on demand
```

## Session behavior

- `/clear` resets the currently active session history.
- `/newchat` creates a fresh session and keeps older sessions available in Agent Zero/browser history.
- `/session` opens a paginated picker for saved sessions from the same Telegram bot + user + chat. Supports inline details navigation and **button-driven search**: tap Search, send a search term, and results filter inline without typing a command. From the details view you can **delete** a session — the on-disk chat file is removed (and a fresh new session is started automatically if you delete the active one).
- `/title` sets a manual session name on the current chat context; `/title auto` clears the manual lock and returns to automatic naming.
- `/topic [name]` opens or resumes a named thread within the same chat; without a name it lists existing topics.
- Session switching is scoped to the same Telegram bot, Telegram user, and Telegram chat for safety.
- When a reply is delivered as voice without a visible text bubble, the optional `📝 Show text` quick action can reveal the text version on demand, including `auto` after voice input.
- `/actions on|off` controls whether the per-reply **More** menu is shown in the current session; the bot default comes from `speech.reply.quick_actions.enabled`.
- From the `/session` picker, open a session's details and tap **🗑 Delete** to remove the chat file. The active session can also be deleted — a fresh new session is started automatically afterwards. Deletion is **button-driven** (no `/session delete` text command) and applies to bound sessions plus any unbound web session whose `CTX_TG_USER_ID` matches the current Telegram user.
- The picker details view also shows a 📝 **Summary** block generated fresh via the utility LLM when you open a session's details. Use `/shortcut summary` on the active session to get a fuller utility-LLM summary in a separate message.

## Notes

- Voice notes are converted to `.ogg/opus` when possible (`ffmpeg` if available). If TTS fails, the plugin falls back to text.
- For OpenAI-compatible Gemini PCM (`format: "pcm"`), the plugin assumes raw PCM `s16le`, `24000 Hz`, mono and converts it automatically before sending to Telegram.
- API keys may use `${ENV_VAR}` or `os.environ/ENV_VAR` style values as documented in the plugin UI.
- Python imports use `usr.plugins.telegram_integration_voice` (see a0-create-plugin).
- **Rich Messages**: final assistant replies can opt into Telegram Bot API native rich rendering for tables, task lists, headings, details, and math via `rich_messages.enabled` or the WebUI toggle. The default stays off for copyability and client compatibility; live draft previews remain on the existing path unless `rich_messages.drafts_enabled` is enabled by a future implementation.
- **Inline buttons**: commands like `/detail`, `/voice`, `/optimize_output`, `/project`, `/model`, and `/shortcut` show inline keyboards when called without arguments. The agent can also present Approve / Cancel choices for risky actions.
- **Unauthorized access**: users not in `allowed_users` receive a throttled reply with their Telegram user ID so they can request access from the operator.
- Publishing to the Plugin Index: use `name` without a leading underscore. The exact Plugin Index repository/path is not part of this repo; verify current upstream publishing instructions before opening an index PR.

## TTS troubleshooting

See [docs/troubleshooting-tts.md](docs/troubleshooting-tts.md) (Docker log filters, `agent.number`, `speech.tts.enabled`).

## License

See [LICENSE](LICENSE).
