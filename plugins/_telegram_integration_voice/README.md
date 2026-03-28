# Telegram Integration (Voice)

Custom Agent Zero Telegram plugin with pluggable Voice features:

- **STT (incoming voice/audio -> text)**
- **TTS (outgoing text -> Telegram voice message)**
- Supports **OpenAI-compatible APIs** (incl. internal **LiteLLM**), **ElevenLabs**, **custom HTTP endpoints**, plus optional local engines.

## Plugin ID

- **Folder / name**: `_telegram_integration_voice`
- **Title**: `Telegram Integration (Voice)`

## What it adds on top of Telegram integration

1. **Voice input transcription (STT)**
   - If user sends voice/audio and STT is enabled, transcript is injected into the user message as:
     - `[Voice transcript] ...`

2. **Voice output replies (TTS)**
   - Bot can send Telegram voice replies (`send_voice`) using configured TTS provider.
   - Reply mode:
     - `off` = never
     - `auto` = when last user input was voice/audio
     - `force` = always

3. **Provider abstraction**
   - STT providers: `openai_compatible`, `elevenlabs`, `custom_http`, `local_whisper`
   - TTS providers: `openai_compatible`, `elevenlabs`, `custom_http`, `kokoro_local`

4. **Agent-level voice override (optional)**
   - `response` tool may pass:
     - `voice_mode: off|auto|force`
     - `voice: true|false`

## Quick install (custom plugin)

Copy this plugin folder into your Agent Zero `plugins/` directory:

- `plugins/_telegram_integration_voice/`

Then enable/configure it in Plugin settings.

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
        base_url: "http://litellm.internal:4000/v1"
        api_key: "${LITELLM_API_KEY}"
        model: "whisper-1"
        language: "de"
        timeout_sec: 60

      tts:
        enabled: true
        provider: openai_compatible
        base_url: "http://litellm.internal:4000/v1"
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

- For Telegram voice notes, output is converted to `.ogg/opus` where possible (`ffmpeg` used if available).
- If TTS fails, plugin falls back to normal text reply.
- API key field supports:
  - direct key (`sk-...`)
  - `${ENV_VAR}`
  - `os.environ/ENV_VAR`

## Important files

- `helpers/speech.py` — STT/TTS provider clients + audio conversion
- `helpers/handler.py` — STT on inbound, TTS/voice mode on outbound
- `helpers/telegram_client.py` — added `send_voice` and `record_voice` action
- `webui/config.html` + `webui/telegram-config-store.js` — speech settings UI
