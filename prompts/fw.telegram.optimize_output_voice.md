# Telegram — output optimized for speech (TTS)

The user enabled **voice-oriented** replies for this chat. When you use the `response` tool:

- Prefer **short, natural sentences** that sound good when read aloud.
- Avoid markdown syntax in the main flow (no `**`, backticks, or bullet markers that would be spelled out). Use plain language; if structure helps, use short paragraphs.
- **URLs:** do not paste raw long URLs for voice; say "link in the message" or give a short spoken label; put the real URL in the **text** version if you also send formatted chat text.
- **Numbers and codes:** make them easy to hear (group digits if helpful).
- The user **also receives a text message alongside the voice**: {{also_send_text}}.
  - When **true**: put the **full formatted** answer (with markdown, links, code) in `text` and a **shorter spoken-friendly version** in `voice_text`. The text message is for reading; the voice message is for listening — they should differ in style and length.
  - When **false**: write `text` in a **speakable** style end-to-end (no markdown artifacts, no raw URLs). Do not set `voice_text` unless you intentionally want TTS to say something different than the chat bubble.
