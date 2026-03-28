# a0-telegram-w-voice

Agent Zero plugin: **Telegram** with optional **STT/TTS** (voice in, voice out), aligned with the upstream conventions in [a0-create-plugin](https://github.com/agent0ai/agent-zero/blob/main/skills/a0-create-plugin/SKILL.md).

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

- STT for incoming Telegram voice/audio
- TTS for outgoing Telegram voice replies
- Providers: OpenAI-compatible APIs (incl. LiteLLM), ElevenLabs, custom HTTP endpoints, optional local engines

## Configuration example

```yaml
bots:
  - name: my_bot
    enabled: true
    token: "<telegram-bot-token>"
    mode: polling
    allowed_users: ["123456789"]

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
        voice_mode: auto
        also_send_text: true
        max_chars: 700
```

## Notes

- Voice notes are converted to `.ogg/opus` when possible (`ffmpeg` if available). If TTS fails, the plugin falls back to text.
- API keys may use `${ENV_VAR}` or `os.environ/ENV_VAR` style values as documented in the plugin UI.
- Python imports use `usr.plugins.telegram_integration_voice` (see a0-create-plugin).
- Publishing to the Plugin Index: use `name` without a leading underscore; see `packaging/plugin-index/index.yaml.example` for an `a0-plugins` PR template.

## TTS troubleshooting

See [docs/troubleshooting-tts.md](docs/troubleshooting-tts.md) (Docker log filters, `agent.number`, `speech.tts.enabled`).

## License

See [LICENSE](LICENSE).
