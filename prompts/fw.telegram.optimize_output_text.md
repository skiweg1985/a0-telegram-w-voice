# Telegram — output optimized for reading (chat)

The user enabled **text-oriented** replies for this chat. When you use the `response` tool:

- Prioritize **scannable** answers on mobile: clear **bold** for key terms, bullet lists, short paragraphs.
- Follow the Telegram markdown rules from the main Telegram session instructions (allowed formatting, avoid deep nesting and tables).
- The user **also receives a voice message alongside the text**: {{also_send_text}}.
  - When **true**: consider adding optional `voice_text` with a short spoken summary so the audio is not a long markdown read-aloud; keep `text` as the canonical readable version.
  - When **false**: no voice message will be sent — focus entirely on readable formatting.
