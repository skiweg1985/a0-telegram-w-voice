# Worklog (Telegram voice plugin)

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
