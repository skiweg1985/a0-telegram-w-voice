# Worklog (Telegram voice plugin)

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
