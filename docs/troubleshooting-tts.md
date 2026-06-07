# TTS: Logs und typische Ursachen

TTS schreibt **kein eigenes Logfile**. Meldungen erscheinen in den **Docker-/Prozess-Logs** (stdout) des Agent-Zero-Containers.

## In Docker-Logs filtern

```bash
# Beispiel Compose-Service (ersetze <service-name> durch deinen Container/Service)
docker compose logs <service-name> 2>&1 | grep -iE 'Telegram TTS|send_voice|Telegram Voice|auto-reply|chain-end'

# Oder live
docker compose logs -f <service-name> 2>&1 | grep -iE 'TTS|Telegram Voice|auto-reply'
```

Relevante Zeilen (nach Plugin-Version mit Diagnose-Logs):

| Text | Bedeutung |
|------|-----------|
| `Telegram TTS skipped: speech.tts.enabled is false` | `speech.tts.enabled` ist für diese Bot-Config zur Laufzeit aus. |
| `Telegram TTS skipped: voice_mode=auto` | Bei `auto` muss die letzte Nutzereingabe eine Sprachnachricht sein; sonst kein TTS. |
| `Telegram TTS: voice message sent` | TTS und Telegram-Versand sind durchgelaufen. |
| `Telegram TTS failed:` | Fehler bei Synthese oder vor dem Senden (Details in derselben Zeile). |
| `Telegram send_voice failed:` | Upload der Sprachdatei an Telegram fehlgeschlagen. |
| `Telegram auto-reply skipped: agent.number=` | Nur **Agent 0** führt den Chain-End-Versand (inkl. TTS) aus. |
| `Telegram Voice ffmpeg` | Konvertierung für Telegram Voice (ffmpeg fehlt oder Fehler). |

**Hinweis:** LLM-`Response`-Blöcke in den Logs stehen **vor** `process_chain_end`. TTS-Zeilen kommen oft **danach** im selben Stream.

## Checkliste

1. **`speech.tts.enabled: true`** und Provider (z. B. LiteLLM `base_url` / API-Key) in der Bot-Config, die der Chat wirklich nutzt (Projekt/Profil).
2. **`speech.reply.voice_mode`:** bevorzugt die aktuellen Modi `voice_only`, `voice_text`, `auto`, `text_only`, `off`. `auto` spricht nur nach Spracheingabe; `voice_only`/`voice_text` erzwingen TTS. Der Legacy-Wert `force` wird noch akzeptiert, ist aber nur aus Alt-Configs relevant. Pro Session überschreibt `/voice` den Modus.
3. **Agent 0:** Telegram Chain-End-Versand ist nur für `agent.number == 0` aktiv; sonst erscheint eine **Warning** in den Logs.
