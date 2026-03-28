# a0-telegram-w-voice

Custom Agent Zero plugin fork for Telegram with pluggable voice support.

Plugin folder:

- `plugins/_telegram_integration_voice`

Main additions:

- STT for incoming Telegram voice/audio
- TTS for outgoing Telegram voice replies
- Provider abstraction for OpenAI-compatible endpoints (incl. LiteLLM), ElevenLabs, custom HTTP endpoints, and optional local engines.

See plugin docs:

- `plugins/_telegram_integration_voice/README.md`
