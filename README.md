# a0-telegram-w-voice

Agent Zero plugin: **Telegram** with optional **STT/TTS** (voice in, voice out), aligned with the upstream conventions in [a0-create-plugin](https://github.com/agent0ai/agent-zero/blob/main/skills/a0-create-plugin/SKILL.md).

## Install

1. **Disable or remove** the core Telegram plugin (`_telegram_integration`) so only one Telegram integration is active.
2. Copy this repository contents (the plugin root with `plugin.yaml`, `api/`, `helpers/`, etc.) into your Agent Zero tree:

   `usr/plugins/telegram_integration_voice/`

   So you have e.g. `usr/plugins/telegram_integration_voice/plugin.yaml`.

3. Optional: run **`execute.py`** from the Plugins UI (or `python execute.py` in that folder) to install `requirements.txt` into the Agent Zero runtime. If `aiogram` is missing, the plugin can still attempt a runtime install when a bot is enabled.
4. Enable **Telegram Integration (Voice)** under Plugin settings (External) and configure bots.

**Plugin ID:** `telegram_integration_voice` (folder name must match `plugin.yaml` `name`).

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

## License

See [LICENSE](LICENSE).
