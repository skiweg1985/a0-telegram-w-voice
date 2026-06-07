# Telegram UX Enhancements Implementation Plan

> **Historical planning note:** This implementation plan predates several shipped UX features and no longer describes the exact current command set or configuration surface. Treat it as background context only; verify current behavior in `README.md`, `default_config.yaml`, and the code.

> Focus branch: `feat/telegram-ux-enhancements`

**Goal:** Make the Telegram plugin feel more like a modern mobile agent client with better contextual replies, smoother voice conversations, and visible live progress.

**Execution order**

## Phase 1 — Reply-based context awareness
1. Detect when a Telegram message is a reply to an earlier message.
2. Extract a compact, human-readable summary of the referenced message.
3. Inject that reply context into the Agent Zero user prompt.
4. Make bot replies thread back to the user’s reply message so the context is visible in Telegram UI.
5. Support text, captions, and attachment-style artifacts with safe fallbacks.
6. Verify plain text, voice input, and artifact replies.

## Phase 2 — Walkie-talkie voice mode
1. Add a dedicated per-session voice conversation mode (`off`, `voice_only`, `voice_text`, `text_only`).
2. Add `/voice` command + inline controls.
3. Persist session mode in chat state.
4. Force STT on incoming voice and TTS on outgoing replies per mode.
5. Add optional quick actions that can be enabled/disabled in config (for example `show text` in `voice_only`).
6. Do not add a dedicated `continue speaking` button — Telegram's native microphone UI already covers that flow well.
7. Verify transitions between voice and text sessions.

## Phase 3 — Live agent progress streaming
1. Reuse the existing progress edit path as the foundation.
2. Add clearer run lifecycle states (`started`, tool steps, finished, failed).
3. Support detail levels: minimal / normal / verbose.
4. Prevent message spam with throttling and dedupe.
5. Handle overlapping runs safely per chat/session.
6. Verify inline response flow and final-in-place behavior.

## Immediate implementation target
Start with **Phase 1: Reply-based context awareness** because it is the smallest UX win with the lowest risk and it improves both text and voice flows.
