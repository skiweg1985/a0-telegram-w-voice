# Worklog (Telegram voice plugin)

> **Historical coordination log:** This file records implementation history and release coordination notes. It intentionally includes superseded branch names, intermediate behavior, and removed commands such as `/tts` or `/alsotext`. Do not use it as the current operational reference; use `README.md`, `default_config.yaml`, and `helpers/command_registry.py` for the current command/config surface.

## 2026-03-30 – Cursor – Release 0.11.2 (plugin.yaml + Changelog)

- Done:
  - `plugin.yaml` Version `0.11.1` → `0.11.2` (Patch: `telegram_bot_cfg` Refresh).
  - `docs/CHANGELOG.md`: Abschnitt `[0.11.2] - 2026-03-30`; Eintrag aus [Unreleased] Fixed nach unten verschoben.
  - `git push origin main` (Commit mit Fix + Release-Metadaten).
- Next:
  - none
- Blockers:
  - none
- Branch/PR:
  - branch: main
  - PR: none
- Files touched:
  - plugin.yaml
  - docs/CHANGELOG.md
  - planning/coordination/WORKLOG.md
- Changelog updated:
  - yes ([0.11.2])

## 2026-03-30 12:00 – Cursor – Plugin-Settings: telegram_bot_cfg bei bestehenden Chats aktualisieren

- Done:
  - Ursache erklärt: Slash-Kommandos schreiben Session-Keys in `ctx.data` und wirken sofort; gespeicherte `telegram_bot_cfg` war nur bei neuer Session gesetzt — TTS/STT/Progress nutzten veraltete Plugin-YAML.
  - Fix: Bei Wiederverwendung eines bestehenden `AgentContext` wird `ctx.data[CTX_TG_BOT_CFG]` mit dem aktuellen `bot_cfg` überschrieben (`handler.py` `_get_or_create_context_from_user`).
  - `docs/CHANGELOG.md` [Unreleased] Fixed ergänzt.
- Next:
  - Optional: Version bump nach Release-Entscheid.
- Blockers:
  - none
- Branch/PR:
  - branch: main
  - PR: none
- Files touched:
  - helpers/handler.py
  - docs/CHANGELOG.md
  - planning/coordination/WORKLOG.md
- Test notes:
  - commands: `python3 -m py_compile helpers/handler.py`
  - UI path: Plugin External YAML ändern → ohne `/newchat` nächste Telegram-Nachricht soll neue STT/TTS/Defaults nutzen
- Changelog updated:
  - yes ([Unreleased] Fixed)
- Follow-ups:
  - none

## 2026-06-04 18:14 – Cursor – Telegram Live-Preview Hintergrundversand

- Done:
  - Asynchrones Coalescing fuer Telegram-Live-Response-Preview eingebaut, damit Stream-Chunks nicht mehr auf Telegram-I/O warten.
  - Neue Progress-Config fuer Preview-Kadenz und Buffer-Flush dokumentiert (`live_response_preview_interval_ms`, `live_response_preview_buffer_threshold`).
  - Detail-Status-Updates auf geplante Hintergrund-Edits umgestellt und Tests fuer Worker-/Flush-Verhalten erweitert.
  - `docs/CHANGELOG.md` unter `[Unreleased]` aktualisiert.
- Next:
  - Telegram-Smoke-Test mit echter Streaming-Antwort und `/detail info` nach Deploy.
- Blockers:
  - none
- Branch/PR:
  - branch: feat/telegram-native-draft-streaming
  - PR: https://github.com/skiweg1985/a0-telegram-w-voice/pull/4
- Files touched:
  - README.md
  - default_config.yaml
  - extensions/python/response_stream_chunk/_45_telegram_live_response.py
  - extensions/python/tool_execute_after/_45_telegram_detail_status.py
  - helpers/constants.py
  - helpers/handler.py
  - tests/test_telegram_session_picker.py
  - docs/CHANGELOG.md
  - planning/coordination/WORKLOG.md
- Test notes:
  - commands: `python3 -m unittest discover -s tests -p 'test_telegram_session_picker.py'`
  - endpoints: none
  - UI path: Telegram Chat Live-Preview und Detail-Status
- Changelog updated:
  - yes ([Unreleased] Added/Changed)
- Follow-ups:
  - none

## 2026-03-30 – Cursor – Release 0.11.1 (plugin.yaml + Changelog)

- Done:
  - `plugin.yaml` Version `0.11.0` → `0.11.1` (Patch für voice_mode De-Escalation).
  - `docs/CHANGELOG.md`: Abschnitt `[0.11.1] - 2026-03-30` mit Fixed-Eintrag; Duplikat aus [Unreleased] entfernt.
- Next:
  - none
- Blockers:
  - none
- Branch/PR:
  - branch: main
  - PR: none
- Files touched:
  - plugin.yaml
  - docs/CHANGELOG.md
  - planning/coordination/WORKLOG.md
- Changelog updated:
  - yes ([0.11.1])

## 2026-03-30 – Cursor – voice_mode Agent-Override nur noch de-escalation

- Done:
  - `send_telegram_reply` (handler.py): Override-Logik auf striktes De-Escalation-Prinzip umgebaut. Agent kann `voice_mode` nur noch *senken* (force→auto→off), nie über den effektiven User/Admin-Modus hinaus hochstufen. Rank-basierter Vergleich statt Sonderfälle. `voice: true/false` (`forced_flag`) komplett entfernt — war nur für Eskalation nützlich und durch Memory-Drift anfällig.
  - `_50_telegram_response.py` (Extension): `CTX_TG_FORCE_VOICE_REPLY`-Handling und -Import entfernt.
  - `fw.telegram.system_context_reply.md` (Prompt): `voice_mode (off|auto|force)` und `voice (true|false)` durch reine `voice_mode "off"` Dokumentation ersetzt. Force-Beispiel durch Off-Beispiel (Code-Reply) ersetzt. LLM wird nicht mehr zum Hochstufen inspiriert.
  - `docs/CHANGELOG.md` [Unreleased] / Fixed aktualisiert.
- Next:
  - Smoke: Config `voice_mode: auto`, Agent antwortet mit `voice_mode: force` in tool_args → darf NICHT als Voice kommen (bleibt auto). Agent mit `voice_mode: off` → kein Voice (de-escalation funktioniert).
  - Agent-Memory bereinigen: gespeicherte "prefers voice_mode force" Präferenz löschen.
- Blockers:
  - none
- Branch/PR:
  - branch: main
  - PR: none
- Files touched:
  - helpers/handler.py
  - extensions/python/tool_execute_after/_50_telegram_response.py
  - prompts/fw.telegram.system_context_reply.md
  - docs/CHANGELOG.md
  - planning/coordination/WORKLOG.md
- Test notes:
  - commands: `python3 -m py_compile helpers/handler.py extensions/python/tool_execute_after/_50_telegram_response.py`
- Changelog updated:
  - yes (Unreleased / Fixed)
- Follow-ups:
  - Agent-Memory/Instructions bereinigen: "Per remembered Telegram preference, I should force voice mode" Eintrag löschen.

## 2026-03-30 – Cursor – /status Reply-Zeile ohne Meta-Extras

- Done:
  - `/status` Reply-Zeile: redundante `chat`-Extras entfernt (shaping/detail Session-Overrides steckten bereits in den effektiven Werten). Tote Hilfsfunktion `_status_reply_chat_extras` entfernt.
  - `docs/CHANGELOG.md` [Unreleased] / Changed ergänzt.
- Next:
  - Smoke: `/tts auto` → `/status` zeigt `replies auto`; `/optimize_output voice` → `/status` zeigt `shaping voice`, ohne „chat …"-Suffix.
- Blockers:
  - none
- Branch/PR:
  - branch: main
  - PR: none
- Files touched:
  - helpers/handler.py
  - docs/CHANGELOG.md
  - planning/coordination/WORKLOG.md
- Test notes:
  - commands: `python3 -m py_compile helpers/handler.py`
- Changelog updated:
  - yes (Unreleased / Changed)
- Follow-ups:
  - none

## 2026-03-30 – Cursor – agent voice_mode override darf Config off nicht umgehen

- Done:
  - `send_telegram_reply`: Modus-Ermittlung umgebaut. `effective_voice_reply_mode()` (Config + Session = /status) ist jetzt die Autorität. Wenn effective = "off", kann der Agent per `voice_mode: force` oder `voice: true` nicht hochstufen. Alter Code ließ `override_mode` komplett an Config vorbei.
  - `docs/CHANGELOG.md` [Unreleased] / Fixed aktualisiert.
- Next:
  - Smoke: Config `voice_mode: off`, Agent antwortet mit `voice_mode: force` → TTS darf **nicht** gesendet werden. Dann Config `voice_mode: auto` → nur bei Voice-Input TTS.
- Blockers:
  - none
- Branch/PR:
  - branch: main
  - PR: none
- Files touched:
  - helpers/handler.py
  - docs/CHANGELOG.md
  - planning/coordination/WORKLOG.md
- Test notes:
  - commands: `python3 -m py_compile helpers/handler.py`
- Changelog updated:
  - yes (Unreleased / Fixed)
- Follow-ups:
  - Agent-Memory/Instructions prüfen: Agent hat "Per remembered Telegram preference, I should force voice mode" — das sollte bereinigt werden (ist aber ein Agent-Prompt-Thema, nicht Code).

## 2026-03-30 – Cursor – also_send_text + voice_text fallback

- Done:
  - `send_telegram_reply`: bei `also_send_text` und leerem `text` Fallback auf `voice_text` für die Textnachricht; `speech._coerce_bool` für `speech.reply.also_send_text`.
  - `docs/CHANGELOG.md` [Unreleased] / Fixed ergänzt.
- Next:
  - Smoke: Voice-Antwort mit nur `voice_text`, Config also_send_text an.
- Blockers:
  - none
- Branch/PR:
  - branch: main
  - PR: none
- Files touched:
  - helpers/handler.py
  - helpers/speech.py
  - docs/CHANGELOG.md
  - planning/coordination/WORKLOG.md
- Test notes:
  - commands: `python3 -m py_compile helpers/handler.py helpers/speech.py`
- Changelog updated:
  - yes (Unreleased / Fixed)
- Follow-ups:
  - none

## 2026-03-30 – Cursor – voice_mode auto vs response voice=true

- Done:
  - `send_telegram_reply`: `forced_flag` (response tool `voice=true`) setzt bei Basis-Modus **auto** kein **force** mehr; Abgleich mit `effective_voice_reply_mode` / `/status`.
  - `docs/CHANGELOG.md` [Unreleased] / Fixed ergänzt.
- Next:
  - Smoke: `speech.reply.voice_mode: auto`, Antwort mit `voice: true` → TTS nur bei Voice-Input (auto), nicht immer.
- Blockers:
  - none
- Branch/PR:
  - branch: main
  - PR: none
- Files touched:
  - helpers/handler.py
  - docs/CHANGELOG.md
  - planning/coordination/WORKLOG.md
- Test notes:
  - commands: `python3 -m py_compile helpers/handler.py`
- Changelog updated:
  - yes (Unreleased / Fixed)
- Follow-ups:
  - none

## 2026-03-30 – Cursor – Status-/Detail-/TTS-Copy

- Done:
  - `speech.effective_voice_reply_mode`, `detail_status.detail_level_display` (debug → verbose in UI); `/status` Voice/Reply-Zeilen (`replies`, `chat`, keine „default“-Meta).
  - `/detail` Button Verbose, Slash-Alias `verbose`, Kurztexte ohne bot/session-Override-Klammern; `/tts` und `/optimize_output` ohne Meta-Klammern.
  - `helpers/command_registry.py`, `README.md`, `docs/CHANGELOG.md` angepasst.
- Next:
  - Telegram smoke: `/status`, `/detail`, `/tts`, `/optimize_output`.
- Blockers:
  - none
- Branch/PR:
  - branch: main
  - PR: none
- Files touched:
  - helpers/handler.py
  - helpers/speech.py
  - helpers/detail_status.py
  - helpers/command_registry.py
  - README.md
  - docs/CHANGELOG.md
  - planning/coordination/WORKLOG.md
- Test notes:
  - commands: `python3 -m py_compile helpers/handler.py helpers/speech.py helpers/detail_status.py`
- Changelog updated:
  - yes (Unreleased / Changed)
- Follow-ups:
  - none

## 2026-03-30 – Cursor – /status OpenClaw-style layout

- Done:
  - `handle_status` in `helpers/handler.py`: flache Zeilenliste (ein Thema pro Zeile), Header mit Bot-Name, Reihenfolge Activity → Chat/Utility → Context → Voice → Reply → Project → Session; Overrides in einer Zeile; Hilfsfunktionen für Modell-Anzeige und Overrides.
  - `docs/CHANGELOG.md` [Unreleased] / Changed ergänzt.
- Next:
  - Manuelles `/status` in Telegram nach Deploy.
- Blockers:
  - none
- Branch/PR:
  - branch: main
  - PR: none
- Files touched:
  - helpers/handler.py
  - docs/CHANGELOG.md
  - planning/coordination/WORKLOG.md
- Test notes:
  - commands: `python3 -m py_compile helpers/handler.py`
  - endpoints: none
  - UI path: Telegram `/status` mit und ohne Session
- Changelog updated:
  - yes (Unreleased / Changed)
- Follow-ups:
  - none

## 2026-03-29 – Cursor – Step icons, labels, 4096 guard

- Done:
  - `step_icon_for_tool` mit Built-in-Map + Prefix-Regeln + Config-Overrides in `helpers/detail_status.py`.
  - `format_step_html` fuer info und debug: Emoji-Prefix + Kurzlabel; Debug-JSON auf konfigurierbare Laenge begrenzt (`telegram_detail_max_body_chars`, Default 3200).
  - Zentraler Guard in `send_telegram_progress_update` (`helpers/handler.py`): finale HTML-Zeichenkette wird auf 4096 Zeichen begrenzt bevor sie an Telegram API geht.
  - Neue Bot-Config-Keys: `telegram_detail_icons_enabled`, `telegram_detail_tool_icons`, `telegram_detail_max_body_chars` in default_config, WebUI store, README.
  - Version 0.11.0.
- Next:
  - Optional: Phasen-Extensions (util_model_call_after / reasoning_stream) falls Web-UI-Phasen in Telegram sichtbar werden sollen.
- Blockers:
  - none
- Branch/PR:
  - branch: main
  - PR: none
- Files touched:
  - helpers/detail_status.py
  - helpers/handler.py
  - default_config.yaml
  - webui/telegram-config-store.js
  - README.md
  - docs/CHANGELOG.md
  - plugin.yaml
  - planning/coordination/WORKLOG.md
- Test notes:
  - commands: `/detail info` und `/detail debug` in Telegram; verifiziere Icon vor Step-Zeile
  - endpoints: none
  - UI path: Telegram Chat
- Changelog updated:
  - yes (Unreleased / Added + Changed)
- Follow-ups:
  - Testen mit echten Tool-Ausfuehrungen (memory_load, text_editor:read, code_execution)

## 2026-03-29 – Agent – /status Telegram layout

- Done:
  - `/status`-Ausgabe in `helpers/handler.py` in thematische HTML-Blöcke mit Absatzabstand gruppiert; einheitliche Zeilen (`·`), klarere Sektionstitel und Override-Zeilen mit Bullet.
- Next:
  - none
- Blockers:
  - none
- Branch/PR:
  - branch: main (lokal)
  - PR: none
- Files touched:
  - helpers/handler.py
  - docs/CHANGELOG.md
  - planning/coordination/WORKLOG.md
- Test notes:
  - commands: manuell `/status` in Telegram nach Deploy
  - endpoints: none
  - UI path: Telegram Chat
- Changelog updated:
  - yes (Unreleased / Changed)
- Follow-ups:
  - none

## 2026-03-30 09:40 – Cursor – Voice/Text Auto + /alsotext Session Toggle

- Done:
  - `optimize_output` um `auto` erweitert (`speech.py`, `handler.py`, Prompt-Injection): pro Turn automatische Aufloesung in voice/text anhand effektivem Voice-Modus und Input-Typ.
  - Neuer Session-Override fuer `also_send_text` mit Key `telegram_also_send_text_session` und Resolver `effective_also_send_text`.
  - Neuer Slash-Command `/alsotext [on|off|reset]` inkl. Inline-Buttons und Callback-Handling.
  - `send_telegram_reply` auf session-aware `also_send_text` umgestellt.
  - Prompts `fw.telegram.optimize_output_voice.md` und `fw.telegram.optimize_output_text.md` auf klare Trennung `text` vs `voice_text` angepasst (inkl. `also_send_text`-Kontext).
  - `/status` Reply-Zeile zeigt jetzt `also text on/off`.
  - `default_config.yaml` Kommentar aktualisiert (empfohlener Default `optimize_output_default: auto`).
- Next:
  - Telegram Smoke-Test: `/optimize_output auto`, `/tts auto|force`, `/alsotext on|off|reset`, danach Voice/Text-Ausgabe vergleichen.
- Blockers:
  - none
- Branch/PR:
  - branch: main
  - PR: none
- Files touched:
  - helpers/constants.py
  - helpers/speech.py
  - helpers/handler.py
  - helpers/command_registry.py
  - extensions/python/system_prompt/_20_telegram_context.py
  - extensions/python/job_loop/_10_telegram_bot.py
  - prompts/fw.telegram.optimize_output_voice.md
  - prompts/fw.telegram.optimize_output_text.md
  - default_config.yaml
  - docs/CHANGELOG.md
  - planning/coordination/WORKLOG.md
- Test notes:
  - commands: `python3 -m py_compile helpers/handler.py helpers/speech.py extensions/python/system_prompt/_20_telegram_context.py extensions/python/job_loop/_10_telegram_bot.py`
  - endpoints: none
  - UI path: Telegram Chat (`/status`, `/optimize_output`, `/tts`, `/alsotext`)
- Changelog updated:
  - yes ([Unreleased] Added/Changed)
- Follow-ups:
  - Optional: WebUI-Dropdown fuer `optimize_output=auto` und Session-`alsotext` Sichtbarkeit in Config-UI.

## 2026-03-30 09:44 – Cursor – Release 0.11.3 (plugin.yaml + Changelog)

- Done:
  - `plugin.yaml` Version `0.11.2` → `0.11.3` angehoben.
  - `docs/CHANGELOG.md`: neuer Abschnitt `[0.11.3] - 2026-03-30` (Added/Changed) erstellt und die zugehoerigen Punkte aus `[Unreleased]` verschoben.
  - Push auf `origin/main`.
- Next:
  - none
- Blockers:
  - none
- Branch/PR:
  - branch: main
  - PR: none
- Files touched:
  - plugin.yaml
  - docs/CHANGELOG.md
  - planning/coordination/WORKLOG.md
- Test notes:
  - commands: none (release metadata only)
  - endpoints: none
  - UI path: none
- Changelog updated:
  - yes ([0.11.3])
- Follow-ups:
  - none

## 2026-06-04 18:21 – Cursor – Voice-only reveal button on voice message

- Done:
  - `send_voice` accepts an optional `buttons` inline keyboard and passes it as `reply_markup`.
  - Reworked `send_telegram_reply` so the "Show text" quick action button is attached to the voice message in `voice_only` mode instead of forcing a separate text bubble.
  - `should_send_text` no longer becomes true just because the reveal button exists; text is only revealed on button tap, with text fallback kept for failed voice delivery.
- Next:
  - none
- Blockers:
  - none
- Branch/PR:
  - branch: main
  - PR: none
- Files touched:
  - helpers/telegram_client.py
  - helpers/handler.py
  - docs/CHANGELOG.md
- Test notes:
  - commands: /voice voice_only then send a message; verify only a voice note with a "Text anzeigen" button appears, tapping it posts the text
  - endpoints: none
  - UI path: Telegram chat (voice_only mode)
- Changelog updated:
  - yes ([Unreleased] Fixed)
- Follow-ups:
  - none

## 2026-06-04 18:33 – Cursor – Persist voice_only "Text anzeigen" reveal token

- Done:
  - `CTX_TG_LAST_TEXT_RESPONSE` and `CTX_TG_LAST_TEXT_RESPONSE_TOKEN` now use non-underscore keys so persist_chat stores them in chat.json.
  - `send_telegram_reply` calls `save_tmp_chat(context)` after sending so the reveal token/text reaches chat.json.
  - `/clear` removes the stored reveal text/token.
- Next:
  - none
- Blockers:
  - none
- Branch/PR:
  - branch: main
  - PR: none
- Files touched:
  - helpers/constants.py
  - helpers/handler.py
  - docs/CHANGELOG.md
- Test notes:
  - commands: /voice voice_only, send a message, restart bot, tap "Text anzeigen"; then /clear and verify old button reports unavailable
  - endpoints: none
  - UI path: Telegram chat (voice_only mode)
- Changelog updated:
  - yes ([Unreleased] Fixed)
- Follow-ups:
  - none

## 2026-06-04 – Cursor – Progress bubble title In progress

- Done:
  - Progress status title `🧠 Working…` → `🔄 In progress…` in `_progress_status_title`.
  - Unit test for rendered progress HTML title.
  - Changelog [Unreleased] Changed.
- Next:
  - none
- Blockers:
  - none
- Branch/PR:
  - branch: feat/telegram-native-draft-streaming
  - PR: none
- Files touched:
  - helpers/handler.py
  - tests/test_telegram_session_picker.py
  - docs/CHANGELOG.md
- Test notes:
  - commands: `python -m pytest tests/test_telegram_session_picker.py -k in_progress_title -q`
  - endpoints: none
  - UI path: Telegram progress bubble during agent run
- Changelog updated:
  - yes ([Unreleased] Changed)
- Follow-ups:
  - none

## 2026-06-04 20:55 – Cursor – Settings & Commands bereinigt

- Done:
  - WebUI/Store auf nutzerrelevante Keys reduziert; Detail-Throttling/Labels/Icons, Progress-Edit-Throttle und Preview-Chars, STT/TTS-Endpoint, STT-Language und Timeouts sind jetzt YAML-only (Merge bewahrt sie über UI-Edits).
  - Voice-Modell vereinheitlicht: ein 5-Modus-Dropdown (off|auto|voice_only|voice_text|text_only) statt mode + "Also send text"-Toggle; `speech._config_voice_reply` mappt neue und alte (`force` + `also_send_text`) Werte abwärtskompatibel.
  - `/speakstyle` entfernt (Menü, Job-Loop-Registrierung, Handler-Zweige); `/clear`-Hilfetext korrigiert (kein nicht-existentes `/reset`).
  - `/alsotext` entfernt (Handler, Inline-Keyboard, Callback `a`, Menü, Registrierung); `effective_also_send_text` liest Altsession-Override weiter, `/clear` poppt ihn.
  - Legacy `/tts`-Fallback entfernt: `CTX_TG_TTS_OVERRIDE`, Callback `t`, speech.py-Fallback und Clear-Pop.
  - `optimize_output_default`-Default in YAML auf `off` angeglichen (Code/README).
  - Neuer Test `tests/test_telegram_voice_reply_mode.py` für das Mapping; gesamte Suite grün (52 Tests).
- Next:
  - none
- Blockers:
  - none
- Branch/PR:
  - branch: feat/telegram-native-draft-streaming
  - PR: none
- Files touched:
  - helpers/speech.py
  - helpers/handler.py
  - helpers/constants.py
  - helpers/command_registry.py
  - extensions/python/job_loop/_10_telegram_bot.py
  - webui/telegram-config-store.js
  - webui/config.html
  - default_config.yaml
  - README.md
  - docs/CHANGELOG.md
  - tests/test_telegram_voice_reply_mode.py
- Test notes:
  - commands: `python3 -m pytest tests/ -q` (52 passed)
  - endpoints: none
  - UI path: WebUI Telegram config (Voice Reply Mode dropdown); Telegram chat (`/voice`, `/optimize_output`, `/detail`, `/status`)
- Changelog updated:
  - yes ([Unreleased] Changed + Removed)
- Follow-ups:
  - none

## 2026-06-04 18:44 – Cursor – Voice-Commands konsolidiert (/tts entfernt)

- Done:
  - `/tts` Command vollständig entfernt (Handler, Inline-Keyboard, Callback `t`, Dispatch, Menü/Help).
  - `/voice` um Modus `auto` erweitert (Sprachantwort nur bei Sprach-Eingabe); neuer Auto-Button im Inline-Keyboard.
  - `speech.effective_voice_reply_mode`: `auto`-Voice-Mode → `auto`; `CTX_TG_TTS_OVERRIDE` nur noch Legacy-Fallback für Altsessions.
  - Reset/Newchat poppt jetzt auch `CTX_TG_VOICE_CONVERSATION_MODE`.
  - README/CHANGELOG/troubleshooting-tts aktualisiert.
- Next:
  - none
- Blockers:
  - none
- Branch/PR:
  - branch: feat/telegram-native-draft-streaming
  - PR: none
- Files touched:
  - helpers/speech.py
  - helpers/handler.py
  - helpers/command_registry.py
  - helpers/constants.py
  - extensions/python/job_loop/_10_telegram_bot.py
  - README.md
  - docs/CHANGELOG.md
  - docs/troubleshooting-tts.md
- Test notes:
  - commands: `/voice` (Buttons inkl. Auto), `/voice auto` + Text → Text, `/voice auto` + Voice → Voice, `/voice voice_only|voice_text|text_only|off`, `/status`
  - endpoints: none
  - UI path: Telegram Chat (/voice, /status)
- Changelog updated:
  - yes ([Unreleased] Changed)
- Follow-ups:
  - none

## 2026-06-04 21:12 – telegram-ux – UX/UI-Potenziale umgesetzt

- Done:
  - Slash-Commands auf reine Modus-Umschaltung umgestellt: Reset/Default-Buttons und `reset`/`default`-Args aus `/detail` und `/optimize_output` entfernt; `/voice off`-Copy bereinigt.
  - `/start`- und `/help`-Copy auf Voice/Status/Modus-Umschaltung ausgerichtet.
  - Englische Locale vereinheitlicht (Reveal-Button "Show text" statt "Text anzeigen").
  - Session-Suche per Force-Reply: Such-Button armiert eine Einmal-Erfassung der nächsten Nachricht als Suchbegriff.
  - Klare, gedrosselte Auth-Meldung für nicht-whitelistete User inkl. eigener Telegram-User-ID.
  - Typing-Indicator wird nach jeder neuen Progress-Nachricht erneut gesendet (Hermes-Pattern).
  - Sichtbare "Still working"-Notiz nach mehreren flood-control-bedingten Progress-Skips (einmalig pro Lauf).
  - `/retry` (letzte Nachricht erneut) und `/undo` (letztes Topic aus History entfernen) implementiert und registriert.
  - Approval/Clarify als Agent-Pattern über das `response`-Tool-Keyboard im System-Prompt verankert (Tastendruck läuft bereits in die Agent-Loop zurück).
  - WebUI: Defaults-Banner, Answer-Style- und Tool-Detail-Selects, Walkie-Talkie-Preset, Preview-Kadenz/Buffer (operator) ergänzt; chat-überschreibbare Felder als Defaults mit Slash-Command-Hinweis gelabelt.
  - `/topic [name]` als benannte Parallel-Session auf Basis der bestehenden Session-Infrastruktur.
- Next:
  - none
- Blockers:
  - none
- Branch/PR:
  - branch: (current)
  - PR: none
- Files touched:
  - helpers/handler.py
  - helpers/command_registry.py
  - helpers/constants.py
  - helpers/telegram_client.py
  - extensions/python/job_loop/_10_telegram_bot.py
  - extensions/python/system_prompt/_20_telegram_context.py
  - prompts/fw.telegram.system_context_reply.md
  - webui/config.html
  - webui/telegram-config-store.js
  - tests/test_telegram_session_picker.py
  - docs/CHANGELOG.md
- Test notes:
  - commands: `python3 -m pytest tests/ -q` (52 passed)
  - endpoints: none
  - UI path: Telegram chat (`/start`, `/help`, `/voice`, `/optimize_output`, `/detail`, `/session`, `/topic`, `/retry`, `/undo`); WebUI Telegram config (defaults, Answer Style, Tool Detail, Walkie-talkie preset, preview tuning)
- Changelog updated:
  - yes ([Unreleased] Added/Changed)
- Follow-ups:
  - none

## 2026-06-04 21:51 – GPT-5.5 – Progress Settings WebUI

- Done:
  - WebUI-Abschnitt "Progress Message Editing" entfernt.
  - Progress-Verhalten im Handler fest verdrahtet: Progress-Edits, Live-Preview, finales In-Place-Edit und Native-Draft-Fallback laufen automatisch.
  - Entfernte Progress-Toggles aus Store-Defaults, Beispielkonfiguration und README entfernt; YAML-only Operator-Tuning bleibt erhalten.
  - Tests auf das neue Config-Modell ohne Progress-Toggles angepasst.
- Next:
  - none
- Blockers:
  - none
- Branch/PR:
  - branch: feat/telegram-native-draft-streaming
  - PR: none
- Files touched:
  - helpers/handler.py
  - webui/config.html
  - webui/telegram-config-store.js
  - default_config.yaml
  - README.md
  - tests/test_telegram_session_picker.py
  - tests/test_telegram_flood_control.py
  - docs/CHANGELOG.md
  - planning/coordination/WORKLOG.md
- Test notes:
  - commands: `python3 -m pytest tests/test_telegram_session_picker.py tests/test_telegram_flood_control.py -q` (38 passed); `python3 -m pytest tests/ -q` (52 passed)
  - endpoints: none
  - UI path: WebUI Telegram bot config; Progress Message Editing section removed
- Changelog updated:
  - yes ([Unreleased] Removed)
- Follow-ups:
  - none

## 2026-06-05 – Auto – Telegram reply keyboard & media delivery polish

- Done:
  - Outbound-Planung für Captions, Inline-Keyboards und Albums (`_plan_outbound_delivery`).
  - `send_voice` unterstützt `reply_markup` für Voice-only mit Reply-Keyboard.
  - Agent-Prompt für Attachments, Captions und Keyboard-Muster erweitert.
  - Unit-Tests für Keyboard-Persistenz, Caption-Routing und Voice-only-Keyboard ergänzt.
- Next:
  - none
- Blockers:
  - none
- Branch/PR:
  - branch: codex/upgrade
  - PR: https://github.com/skiweg1985/a0-telegram-w-voice/pull/6
- Files touched:
  - helpers/handler.py
  - helpers/telegram_client.py
  - prompts/fw.telegram.system_context_reply.md
  - tests/test_telegram_media_routing.py
  - tests/test_telegram_session_picker.py
  - docs/CHANGELOG.md
  - planning/coordination/WORKLOG.md
- Test notes:
  - commands: `python -m pytest tests/test_telegram_media_routing.py tests/test_telegram_session_picker.py -q` (53 passed)
  - endpoints: none
  - UI path: Telegram DM reply keyboard + media replies
- Changelog updated:
  - yes ([Unreleased] Changed)
- Follow-ups:
  - none

## 2026-06-06 – Auto – Telegram response transform quick actions

- Done:
  - Inline-Buttons **Shorter**, **More technical** und **Step by step** an Text-Antworten ergänzt.
  - Callback-Handler dispatcht Transform als internen Follow-up-Turn auf Basis der gespeicherten letzten Antwort.
  - Unit-Tests für Keyboard-Layout und Transform-Callbacks ergänzt.
- Next:
  - none
- Blockers:
  - none
- Branch/PR:
  - branch: codex/upgrade
  - PR: https://github.com/skiweg1985/a0-telegram-w-voice/pull/6
- Files touched:
  - helpers/handler.py
  - tests/test_telegram_session_picker.py
  - docs/CHANGELOG.md
  - planning/coordination/WORKLOG.md
- Test notes:
  - commands: `python3 -m unittest discover -s tests -p 'test_telegram_session_picker.py' -v` (52 passed)
  - endpoints: none
  - UI path: Telegram inline response action keyboard
- Changelog updated:
  - yes ([Unreleased] Added)
- Follow-ups:
  - none
