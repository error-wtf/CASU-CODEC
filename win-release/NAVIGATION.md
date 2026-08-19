# NAVIGATION — Master-Index über alle Hilfsdateien

Zweck: Beim Portieren nie suchen müssen — dieses Dokument sagt, WO welche
Information steht. Pfade relativ zu `win-release/`.

## 0. START (für neue Portierungs-Session)
| Datei | Inhalt |
|-------|--------|
| `START_HIER.md` | **Start-Prompt** für die neue Session (in neue Session kopieren) |
| `PREREQUISITES.md` | was vor dem Portieren beschafft werden muss (SCHRITT 0) |
| Datei | Inhalt | Wann lesen |
|-------|--------|-----------|
| `PORT_STATUS.md` | aktueller Fortschritt, aktueller Schritt | Start jeder Sitzung |
| `WINDOWS_PORT_BASELINE.md` | eingefrorener Referenzstand (SHA, Tests, Komponenten) | einmalig, Kontext |
| `README_WINDOWS.md` | Zielarchitektur + Toolchain | Kontext |
| `WINDOWS_INSTALL_AND_CODEC.md` | **Installation (PATH/Dateitypen) + Media-Codec-Entscheidung (MF/DirectShow geplant), Linux-Kompatibilität** | bei Install-/Codec-/Upgrade-Fragen |
| `research/PROMPT_REQUIREMENTS_LEDGER.md` | verbindliche Anforderungen (REQ-IDs, harte Regeln) | bei jeder Abweichung |
| `PREREQUISITES.md` | was vor dem Portieren beschafft werden muss (fehlende Windows-Runtime) | **SCHRITT 0** der neuen Session |

## 2. Referenz verstehen (research/)
| Datei | Kerninhalt | Schlüsselwörter |
|-------|-----------|-----------------|
| `SYSTEM_UNDERSTANDING_MASTER.md` | Gesamtsynthese (CASU/MPCASU/Web/Converter, Architektur, Invarianten) | Gesamtbild |
| `repository-inventory.md` | alle Komponenten + Entry-Points + Windows-Zuordnung | Inventar |
| `casu-format-deep-dive.md` | CASU/NAT1/NAT2/MP5 binär, Magic, Limits, zstd, Golden | **Format** |
| `player-mechanics.md` | Playback-Ablauf, Backend-Interface, Lifecycle-Fallen | **Player** |
| `state-machines-and-flows.md` | Zustandsmaschinen, Datenflüsse, Threading/Ownership | **State** |
| `ui-style-bible.md` | Palette/Metrik/Layout/Provenienz (Design-Tokens) | **UI** |
| `web-api-contract.md` | alle Web-Endpoints + Security | **Web-API** |
| `youtube-transport.md` | Transport-Vertrag + Lifecycle-Regel | **YouTube-Transport** |
| `api-contracts-errors-shutdown.md` | Backend-Interface, Fehlermodell, Shutdown | **API/Fehler** |
| `windows-technology-map.md` | Linux→Windows-Mapping | **Mapping** |
| `windows-audio-design.md` | PulseAudio→WASAPI/Qt | **Audio** |
| `webplayers-and-legacy.md` | WebPlayerTabs, play_video=OBSOLETE, mpcasu_web=OBSOLETE | **Legacy** |
| `vlc-and-webamp-reference.md` | libVLC API, Webamp-Idiom, Provenienz | **VLC/Webamp** |
| `design-history.md` | warum Dinge so sind (Git-Historie) | **Historik** |
| `completeness-remaining-files.md` | restl. Dateien klassifiziert, Lizenzen, Fixtures | **Reste** |
| `UNDERSTANDING_CHECK.md` | 25 Fragen beantwortet | Verifikation |
| `external-research-log.md` | (bei Bedarf füllen) Deep-Research-Ergebnisse | bei Fragen |

## 3. Fahrpläne (roadmap/)
| Datei | Inhalt |
|-------|--------|
| `MASTER_WINDOWS_PORT_ROADMAP.md` | Milestones/Epics/Work-Packages (M1–M6) |
| `EXECUTION_PLAN.md` | 30 Schritte, geordnet nach Dependencies |
| `CRITICAL_PATH.md` | was zuerst stabilisieren + Risiko-Register |
| `TOOL_DEPENDENCY_AND_AUDIT.md` | Tool-Graph, Per-Tool-Audit, Port-Status |
| `REQUIREMENT_COVERAGE_AND_AUDIT.md` | jede REQ→WP-Zuordnung, Roadmap-Audit |
| `tools/TOOL_INVENTORY.md` | alle Tools + Windows-Artefakte + Priorität |
| `tools/<tool>/PORT_ROADMAP.md` | **pro Tool maximal ausführlicher Fahrplan** |
| `tools/<tool>/ACCEPTANCE_GATE.md` | (mpcasu) Feature-Matrix + Mapping + Gate |
| `libraries/casu-core/PORT_ROADMAP.md` | casu_core WPs |
| `libraries/OTHER_LIBRARIES.md` | casu_codec/media/network/playback/webapi WPs |

## 4. Ausführungs-Regeln (die Run-Dokumente)
| Datei | Inhalt |
|-------|--------|
| `MASTER_GESAMTFAHRPLAN.md` | **DER zusammengeführte, abhakbare Einzelfahrplan** (Phasen A–D, Steps 1–42) |
| `RUN_CHECKLIST.md` | fehlerfreier Arbeits-Loop + harte Gates + Fehlerbehandlung |
| `REFERENCE_LOOKUP.md` | Schlüsselwort → Datei:Zeile (gezieltes Nachschlagen) |
| `roadmap/EXECUTION_PLAN.md` | die 30 Schritte (Sequenz, älter, wird vom Gesamtfahrplan abgelöst) |
| `roadmap/BLOCKERS.md` | Blocker-Log |

## Der Run in 4 Dateien (Merkformel)
- `NAVIGATION.md` = Karte (was wo steht)
- `REFERENCE_LOOKUP.md` = Legende (Referenz auf Datei:Zeile)
- `MASTER_GESAMTFAHRPLAN.md` = Weg (der Einzelfahrplan, abhakbar)
- `RUN_CHECKLIST.md` = Checkliste (der Loop + Gates)

## Kompatibilitäts-Garantie (WICHTIG bei Upgrades)
- **Linux bleibt unangetastet**: Der Referenzbaum `/home/error/Codec-Casu`
  (Code: `casu/`, `mpcasu_qt/`, `mpcasu_*.py`, `web/`, `packaging/`) ist READ-ONLY.
  Alle Windows-Änderungen gehören NUR nach `win-release/`. README.md (Root) ist
  Doku und darf um Windows-Abschnitte ergänzt werden (kein Linux-Funktionscode).
- Vor jedem Commit: `git status --short` — keine Fremdänderung außerhalb
  `win-release/` (+ README.md Doku). Siehe `RUN_CHECKLIST.md`.

## 5. Tests / Ergebnis-Ablage
- `tests/unit|integration|golden|compatibility|wine/` — Tests
- `test-results/compatibility/*.json`, `test-results/wine/` — Ergebnisse
- `audit/session-start.txt` — Start-Audit jeder Sitzung
- `roadmap/BLOCKERS.md` — Blocker-Log

## Merkregel (Token-Effizienz)
Bei einer Aufgabe: (1) `PORT_STATUS.md` → (2) jeweiliges `tools/<tool>/PORT_ROADMAP.md`
→ (3) das eine research-Dokument, das die konkrete Stelle erklärt
(`REFERENCE_LOOKUP.md` sagt welches) → (4) Referenzdatei gezielt per grep lesen.
Nicht alles neu lesen — gezielt nachschlagen.
