# Telegram Next-Level Feature Plan

> **Historical planning note:** This file is a roadmap snapshot, not current product documentation. Several items were shipped, renamed, or superseded after this plan was written. Use `README.md`, `default_config.yaml`, and `helpers/command_registry.py` as the current source of truth for commands and supported behavior.

> Focus branch: `codex/upgrade`

## Status-Legende

- `[x]` fertig
- `[-]` teilweise umgesetzt
- `[ ]` offen

## Ausgangslage

Der aktuelle Stand hat bereits mehrere starke UX-Bausteine:

- Session-Picker mit Suche und Details
- `/title` fuer manuelles Session-Rename mit Auto-Reset
- Voice/Text-Modi inkl. Inline-Aktionen
- Live-Preview waehrend laufender Antworten
- Medienrouting fuer Text, Voice und Artefakte

Wichtig fuer die Priorisierung: `Session umbenennen` ist bereits umgesetzt und sollte nicht mehr als neues Kernfeature geplant werden. Der Ausbau liegt jetzt bei `recent`, `pinned`, `preview`, `continue last` und einem besseren Entry Point fuer bestehende Session-Aktionen.

## Empfohlene Reihenfolge

1. Session UX Layer
2. Inline Action Bar pro Antwort
3. Smarter Artifact Presentation
4. Message-to-Action Flows
5. Antwort-Detailgrad pro Antwort
6. Bessere System-/Status-Messages
7. Antworten transformierbar machen
8. Session-Header / Memory-Hinweise

## Release-Buendel

### Release 1: Navigation & Context

- `[-]` Session UX Layer
- `[-]` Session-Header / Memory-Hinweise
- `[x]` Bessere System-/Status-Messages

### Release 2: Response Interaction

- `[x]` Inline Action Bar pro Antwort
- `[ ]` Antwort-Detailgrad pro Antwort
- `[ ]` Antworten transformierbar machen

### Release 3: Output Quality & Operational Flows

- `[x]` Smarter Artifact Presentation
- `[-]` Message-to-Action Flows

## Feature 1: Session UX Layer

**Status**

- `[-]` Teilweise umgesetzt

**Ziel**

Sessions sollen sich wie echte Arbeitskontexte anfuehlen und schneller wiederauffindbar sein.

**Bereits vorhanden**

- `/title` fuer manuelles Rename
- Session-Suche
- Session-Details mit Titel, Topic und Aktiv-Status

**MVP**

- `[ ]` `continue last session`
- `[ ]` `recent sessions` im Picker sichtbar machen
- `[ ]` `pinned sessions`
- `[ ]` `1-Zeilen-Vorschau` pro Session

**V2**

- Rename direkt aus dem Session-Picker anstossen
- getrennte Sektionen `Pinned`, `Recent`, `All`
- bessere Sortierlogik fuer aktive und zuletzt genutzte Sessions

**Technischer Schnitt**

- Session-Metadaten um `last_used_at`, `pinned`, `preview_text` erweitern
- Vorschau moeglichst aus letzter relevanter User/Assistant-Message ableiten
- Picker-Renderer auf gruppierte Listen statt reine Flat-Page-Liste vorbereiten

**Abhaengigkeiten**

- Persistenz fuer neue Session-Metadaten
- Session-Render-Pipeline in `helpers/handler.py`

**Risiken**

- Preview-Text darf nicht doppelt oder stale gepflegt werden
- Zu viele Sessions im Picker duerfen die Telegram-UI nicht ueberladen

**Akzeptanzkriterien**

- Nutzer kann die zuletzt genutzte Session mit einem Schritt fortsetzen
- Angeheftete Sessions bleiben stabil sichtbar
- Jede Session zeigt eine kurze, hilfreiche Vorschau

**Stand heute**

- `[x]` Session-Picker mit Pagination, Suche und Detailansicht ist vorhanden
- `[x]` Session-Wechsel und neue Session sind per Inline-Buttons erreichbar
- `[ ]` Die geplanten Metadaten `last_used_at`, `pinned`, `preview_text` fehlen noch

## Feature 2: Inline Action Bar pro Antwort

**Status**

- `[x]` Fertig

**Ziel**

Aktionen sollen direkt dort auftauchen, wo die Entscheidung faellt: an der konkreten Antwort.

**MVP**

- `[x]` `Retry`
- `[x]` `Continue`
- `[x]` `New session`
- `[x]` `Show text`

**V2**

- `[ ]` `Pin session`
- `[ ]` `Summarize`
- `[ ]` `Read aloud`

**Technischer Schnitt**

- Inline-Keyboard-Generator nach Nachrichtentyp einziehen
- Antwort-Metadaten so speichern, dass Folgeaktionen auf die letzte Antwort referenzieren koennen
- globale Control-Pad-Logik nur dort behalten, wo kein Antwortkontext existiert

**Abhaengigkeiten**

- Callback-Routing
- Antwort-Metadaten pro Telegram-Message

**Risiken**

- Zu viele Buttons erzeugen erneut UI-Rauschen
- Actions muessen pro Antwortstyp konsistent sein

**Akzeptanzkriterien**

- Antworten zeigen nur kontextrelevante Aktionen
- Haeufige Folgewuensche funktionieren ohne neue freie Texteingabe

**Stand heute**

- `[x]` Antwortbezogene Inline-Buttons werden direkt an Text- oder Voice-Antworten gehaengt
- `[x]` Antwort-Tokens sichern, dass Folgeaktionen deterministisch auf die letzte Antwort zeigen

## Feature 3: Smarter Artifact Presentation

**Status**

- `[x]` MVP fertig

**Ziel**

Artefakte sollen hochwertig, absichtsvoll und Telegram-nativ praesentiert werden.

**MVP**

- `[x]` bessere Entscheidung zwischen `photo` und `file`
- `[x]` Caption statt doppelter Textblase
- `[x]` saubere Kombination aus Text und Artefakt

**V2**

- `[x]` mehrere Bilder als Album
- `[-]` verbesserte Auswahl zwischen `photo`, `file`, `video`, `animation`, `voice`
- `[-]` kurze, sinnvolle Captions statt Redundanz

**Technischer Schnitt**

- zentralen Presentation-Resolver fuer Telegram-Antworttypen einfuehren
- Resolver entscheidet anhand von Artefakttyp, Textlaenge, Anzahl und Fallbacks
- bestehendes Medienrouting konsolidieren statt Sonderfaelle weiter zu verteilen

**Abhaengigkeiten**

- aktuelles Medienrouting in `helpers/handler.py`
- Tests fuer Medien- und Caption-Verhalten

**Risiken**

- Telegram-Limits bei gemischten Medien
- gemischte Text-/Artefakt-Antworten koennen regressionsanfaellig sein

**Akzeptanzkriterien**

- Medienantworten vermeiden doppelte Textblasen
- Mehrere Bilder koennen als Album gesendet werden
- Die Wahl des Telegram-Formats wirkt fuer Nutzer nachvollziehbar und hochwertig

**Stand heute**

- `[x]` Medienrouting deckt Photo, Animation, Video, Video-Note, Dokument und strukturierte `telegram_items` ab
- `[x]` Multi-Image-Antworten koennen als Media Group gesendet werden

## Feature 4: Message-to-Action Flows

**Status**

- `[-]` Teilweise umgesetzt

**Ziel**

Antworten sollen direkt in den naechsten sinnvollen Schritt ueberfuehren.

**MVP**

- `[ ]` nach Code/Datei-Antwort: `Open session`, `Run again`, `Retry with changes`
- `[x]` nach Voice: `Show text`

**V2**

- `[ ]` nach Voice: `Re-speak shorter`
- `[ ]` nach Medien: `Send as files`, `Send as album`

**Technischer Schnitt**

- Action-Mapping pro Antwortklasse
- vorhandene Inline-Action-Bar als Tragerschicht wiederverwenden
- Flows auf wenige, klar erkennbare Antworttypen begrenzen

**Abhaengigkeiten**

- Inline Action Bar
- Antwortklassifikation

**Risiken**

- Zufallsartige Aktionen ohne erkennbare Logik
- zu grosse Ueberschneidung mit allgemeinen Antwort-Aktionen

**Akzeptanzkriterien**

- Fuer definierte Antworttypen gibt es mindestens einen klaren Next Step
- Nutzer koennen haeufige Folgeaktionen per Tap ausloesen

**Stand heute**

- `[x]` Voice-Antworten ohne sichtbare Textblase bieten `Show text`
- `[-]` Allgemeine Folgeaktionen `Retry`, `Continue`, `New session` existieren bereits, sind aber noch nicht feingranular nach Antwortklasse gemappt

## Feature 5: Antwort-Detailgrad pro Antwort

**Status**

- `[ ]` Offen

**Ziel**

Nutzer sollen die Tiefe einer Antwort situativ anpassen koennen, ohne globalen Moduswechsel.

**MVP**

- `Kurz`
- `Normal`
- `Verbose`
- `Nur Ergebnis`

**V2**

- `Mit Tool-Details`

**Technischer Schnitt**

- Antwort-Transformation auf Basis der letzten Assistant-Message
- Detailgrad als expliziter Antwort-Intent statt globales Session-Setting behandeln

**Abhaengigkeiten**

- Inline Action Bar
- Antwort-Transformation / Retry-Mechanik

**Risiken**

- Verwechslung mit `Continue`
- Semantik von `Verbose` und `Mit Tool-Details` muss klar getrennt bleiben

**Akzeptanzkriterien**

- Nutzer koennen eine vorhandene Antwort kurz oder ausfuehrlich neu anfordern
- globales `/detail` bleibt technisch getrennt von inhaltlicher Antworttiefe

## Feature 6: Bessere System-/Status-Messages

**Status**

- `[x]` Fertig

**Ziel**

Systemmeldungen sollen kuerzer, klarer und produktartiger wirken.

**MVP**

- `[x]` einheitliche Texte fuer `running`, `done`, `failed`, `voice processing`, `artifact sent`
- `[x]` redundante technische Texte reduzieren

**V2**

- leichte Varianten je Kontext, ohne den Stil aufzubrechen

**Technischer Schnitt**

- Status-Copy zentralisieren
- vorhandene Statusmeldungen in wenigen, wiederverwendbaren Helpern buendeln

**Abhaengigkeiten**

- Status- und Progress-Pipeline

**Risiken**

- Zu generische Texte verlieren Nuetzlichkeit
- Zu technische Texte bleiben UI-fremd

**Akzeptanzkriterien**

- Statusmeldungen sind konsistent formuliert
- Help-artige oder debughafte Systemtexte werden sichtbar reduziert

**Stand heute**

- `[x]` Zentrale Status-Copy wurde in einen gemeinsamen Helper gezogen
- `[x]` Progress-, Completion- und Failure-Texte nutzen denselben Copy-Layer

## Feature 7: Antworten transformierbar machen

**Status**

- `[ ]` Offen

**Ziel**

Bestehende Antworten sollen weiterbearbeitet werden koennen, statt immer neu gefragt zu werden.

**MVP**

- `Shorter`
- `More technical`
- `Explain step by step`
- `Continue from here`

**V2**

- freie Transform-Prompts auf bestehende Antworten

**Technischer Schnitt**

- letzte Assistant-Message plus Transform-Intent als neuer interner Turn
- klare Trennung zwischen `Antwort umformen` und `Task weiter ausfuehren`

**Abhaengigkeiten**

- Inline Action Bar
- Retry-/Continue-Mechanik

**Risiken**

- Unscharfer Unterschied zwischen Transform und neuem Prompt
- Gefahr von Kontextdrift, wenn alte Antwort nur teilweise transformiert wird

**Akzeptanzkriterien**

- Nutzer koennen eine bestehende Antwort gezielt umformen
- Die resultierende Antwort bleibt sichtbar auf die Ausgangsantwort bezogen

## Feature 8: Session-Header / Memory-Hinweise

**Status**

- `[-]` Teilweise umgesetzt

**Ziel**

Der aktive Kontext soll im Chat jederzeit leicht erkennbar sein.

**MVP**

- `[-]` aktive Session sichtbar machen
- `[x]` Voice/Text-Modus klarer kennzeichnen
- `[x]` Session-Wechsel kurz bestaetigen

**V2**

- kleine Memory-Hinweise bei relevanten Wechseln oder Modus-Aktionen

**Technischer Schnitt**

- leichte Kontextanzeige in Picker, Status oder bestaetigenden Systemmeldungen
- keine schwere permanente Header-UI erzwingen, solange Telegram dies nicht gut traegt

**Abhaengigkeiten**

- Session-Metadaten
- Status-/Systemmeldungen

**Risiken**

- Zu viel Header-Flaeche fuehlt sich schnell schwerfaellig an
- Doppelte Kontextsignale mit Session-Picker und Status

**Akzeptanzkriterien**

- Nutzer sehen bei Session-Wechseln klar, welcher Kontext aktiv ist
- Voice/Text-Modus ist ohne Nachdenken erkennbar

**Stand heute**

- `[x]` `/status` zeigt Session, Voice-Modus und Reply-Modus kompakt an
- `[x]` Session-Wechsel antwortet mit einer bestaetigenden Statusmeldung
- `[ ]` Ein staerkerer, dauerhafter Header-/Memory-Hinweis im laufenden Chat fehlt noch

## Empfohlener Start auf `codex/upgrade`

1. Session UX Layer
2. Inline Action Bar pro Antwort
3. Smarter Artifact Presentation

Diese drei Themen liefern zusammen den staerksten sichtbaren Produkt-Sprung. Sie verbessern Navigation, Interaktion und Ausgabequalitaet, ohne sofort tief in komplexe Agentenlogik eingreifen zu muessen.
