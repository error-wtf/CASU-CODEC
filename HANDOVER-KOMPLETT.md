# CASU / MPCASU — VOLLSTÄNDIGES HANDOVER (Rettungsdokument)

**Datum:** 2026-08-14 (Ende Session 3)
**Repo:** `/home/error/Lino-Codec` · **Version:** 1.0.0-rc8
**Dieses Dokument ist self-contained.** Es fasst `codec-handover.md` zusammen und
ergänzt alles aus Session 2+3: Vorfall, Wiederherstellung, Backups, Fixes, Prüfung.

---

## 0. PFLICHTREGELN FÜR JEDES FOLGE-TOOL (BACKUP-MODUS)

1. **IMMER Backup vor Änderung:** `cp datei datei.bak-$(date +%s)`
2. **NIEMALS `rm -rf`** auf Repos, Arbeitskopien, Benutzerdaten.
3. **Vor DEB-Neubau:** `cp -a dist backups/debs-$(date +%Y%m%d-%H%M)`
   (`packaging/build_debs.sh` löscht `dist/` selbst).
4. **Vor `dpkg --purge/--remove`:** Paketinhalt sichern
   (`dpkg-deb -x` oder Datei-Kopie aus `backups/`).
5. **`~/.config/mpcasu/`** nie ungesichert ändern.
6. Nach jeder Sitzung: dieses Dokument fortschreiben.

---

## 1. DER VORFALL (rm -rf) — bewiesen aus opencode-DB

`~/.local/share/opencode/opencode.db`, Tabelle `part`:

| Zeitpunkt | Session | Befehl |
|---|---|---|
| 08-13 21:59:34 | ses_0034e7658ffe… | `rm -rf /home/error/Lino-Codec-work && mkdir … && tar` |
| 08-13 22:39 | ses_0034e7658ffe… | `rm -rf /home/error/Lino-Codec-work` |
| 08-14 00:41:46 | ses_002bc10b6ffe… | `rm -rf /home/error/Lino-Codec-work` |

Zerstört: Qt-Player-Vorarbeit (`mpcasu_qt/`), Parallel-Webplayer (`mpcasu_web/`),
`casu/media_backend.py`. **Alles wurde aus derselben DB wiederhergestellt** und
ist heute Teil des Repos (siehe Abschnitt 3).

---

## 2. INSTALLATIONSZUSTAND (verifiziert)

Installiert, `dpkg -V` sauber:

| Paket | Version | Hinweis |
|---|---|---|
| casu-codec | 1.0.0-rc8 | Codec + CLI `/usr/bin/casu` |
| casu-converter | 1.0.0-rc8 | `/usr/bin/casu-converter` |
| mpcasu | 1.0.0-rc8 | Desktop-Player `/usr/bin/mpcasu` |
| mpcasu-web | 1.0.0-rc8 | war entfernt, **wieder installiert** aus Backup |
| web-casu | 1.0.0-rc8 | besserer Webplayer `/usr/bin/web-casu` |

Beide Webplayer servieren dieselben Assets (`/usr/share/casu-codec/web/`).
Unterschied nur im Launcher: `web_casu.py` hat zusätzlich Port-Takeover
(`/tmp/opencode` → `artifacts/recovery/mpcasu_web_vs_web_casu.diff` im Repo).

---

## 3. WIEDERHERGESTELLTES MATERIAL (komplett)

### 3.1 Aus der opencode-DB rekonstruiert (52 Dateien)
- Ort: `/home/error/Lino-Codec-work-recovered/`
- Skript: `/home/error/Lino-Codec/artifacts/recovery/db_recovery-script.py`
- Methode: write-Inhalte + edit-Diffs + read-Outputs aus `part`-Tabelle,
  chronologisch repliziert.
- Ins Repo übernommen (Unique, sonst nirgends vorhanden):
  - `mpcasu_qt/` — Qt-Player: `main_window.py` (2045 Zeilen, aus 81-KB-write + 8 edits),
    `theme.py` (440 Zeilen Design-System), `videoframe.py`, `app.py`, `__init__.py`.
    Kompiliert; alle Imports gegen aktuelles Repo aufgelöst. **Braucht PySide6** (nicht installiert).
  - `mpcasu_web/` — Parallel-Webplayer: `player.js` (58 KB, node --check OK), `index.html`
  - `casu/media_backend.py` — abstrakte Backend-Schnittstelle

### 3.2 Alle DEB-Versionen — `/home/error/Lino-Codec/backups/` (alle mit SHA256SUMS, verifiziert)

| Verzeichnis | Inhalt |
|---|---|
| `debs-zip-v2-1.0.0/` | 1.0.0 |
| `debs-zip-v3-rc2/` … `debs-zip-v8-rc7/` | rc2 … rc7 |
| `debs-zip-v9-rc8-zip/` | rc8 (08-08-Zipstand) |
| `debs-2026-08-14-0026/` | rc8-Build 14.08. 00:26 — **inkl. mpcasu-web + web-casu** („da ging alles"-Zustand) |
| `debs-heute/` | heutiger Build mit allen Fixes |

### 3.3 Wheels — `backups/wheels/`
4 verschiedene `casu_codec-1.0.0rc8-py3-none-any.whl` (pip-cache, final, auto-route, audit).

### 3.4 Repo-Snapshots — `backups/repo-snapshots/`
- `casu-install/`, `casu-wheel-check/` (komplett, aus /tmp gerettet)
- `diffs-casu-final-package…/`, `diffs-casu-package-check…/`, `diffs-casu-deb…/`:
  alle Dateien, die sich von den drei großen /tmp-Snapshots zum aktuellen Repo
  unterscheiden (29/28/26 Dateien) — als Referenz konserviert.

### 3.5 Vollbackup des Repos
`/home/error/Lino-Codec-VOLLBACKUP-2026-08-14.tar.gz` (2,7 GB)
SHA256: `e7a4e278cec3ed8984434152daa367c058e5627f49366bd228f5fb14330a42de`
(`.sha256`-Datei liegt daneben; Repo inkl. aller Zips, ohne backups/)

### 3.6 Weitere Quellen (unverändert vorhanden)
- `MPCASU_CASU_latest_v2…v9.zip` im Repo (Snapshot-Zips, 08-13 22:22)
- `/home/error/MPCASU_CASU_latest.zip` (1.0.0, root-owned)
- `/home/error/CASU-CODEC-chatgpt-2026-08-08.zip` (ältere 1.0.0-Variante,
  anderer Codec-Umfang: casu-codec nur 48 KB)
- `/home/error/CASU_RELEASE_GATE_KIT/` (+ Kopie in Downloads) mit
  `helpers/backend_contract.py`, `canonical_models.py`, `native_v2_contract.py`,
  `release_gate_checklist.json`
- `/home/error/tmp_mp5/format.py` (MP5-Format-Arbeit)
- git: Historie intakt, keine Stashes, keine dangling objects, Reflog sauber.

---

## 4. REPO-STRUKTUR & FEATURES (aktueller Stand)

```
/home/error/Lino-Codec/
├── mpcasu_player.py         2927 Zeilen — Tk-Desktop-Player (alle Features)
├── mpcasu_backend.py        libVLC-ctypes-Backend + LegacyCasuBackend
├── mpcasu_native_backend.py CASUNAT2-Decoder (PyAV, Tk-Sink, PulseAudio)
├── mpcasu_playback.py       PlaybackController
├── casu/                    Codec-Paket (core, native, native_v2/, strict/,
│                            mp5/, epg, playlist, library, settings, spotify,
│                            locations, recording, jobs, transcode, export, …)
├── mpcasu_qt/               wiederhergestellter Qt-Player (braucht PySide6)
├── mpcasu_web/              wiederhergestellter Parallel-Webplayer (Referenz)
├── web/                     aktueller Webplayer (app.js, casu-native.js WASM)
├── web_casu.py              Webserver-Launcher
├── casu_converter.py        Converter-GUI
├── packaging/build_debs.sh  DEB-Builder (4 Pakete: codec, converter, mpcasu, web-casu)
├── backups/                 ALLE alten DEBs/Wheels/Snapshots (siehe 3.2–3.4)
├── artifacts/recovery/      Recovery-Skript + mpcasu_web-Diff
├── tests/                   28 Testdateien, 354 Tests gesammelt
└── docs/                    Format-Spec, Provenance, Converter-Doku etc.
```

Player-Features (Auswahl): alle Formate via libVLC, CASUNAT1/2 nativ,
Internet-Streams (HLS/RTSP/HTTP), YouTube/Spotify mit yt-dlp-Consent-Gate,
M3U/PLS + EPG (XMLTV), Aufnahme, Snapshot, A-B-Loop, Bookmarks, Kapitel,
Track-Umschaltung, Equalizer, Settings-Dialog (Volume/Resume/Visualizer/Cache/
Consent/DB-Refresh), Session-Restore, Queue mit Format-Badges + Suche,
Mini-Player, Fullscreen.

---

## 5. FIXES AUS SESSION 2+3 (alle verifiziert)

| Fix | Datei/Stelle |
|---|---|
| Settings-Dialog + Nav-Anbindung | `show_settings_dialog`, `_navigate` |
| yt-dlp-Consent-Gate (Legal Notice) | `_resolve_and_open_external_source` |
| Queue-Format-Badges | `_render_playlist` (+ Test-Update) |
| Visualizer-Modus (spectrum/waveform/both/off) | `_draw_visualizer` |
| Settings-Persistenz der neuen Felder | `casu/settings.py` load(), `_save_effective_settings` |
| **`play_selected` rekonstruiert** (Backend-Open-Pfad war abgeschnitten — lokale Wiedergabe tot) | `mpcasu_player.py` |
| Database-Tab-Crash (`total_count` existierte nicht) | `_refresh_db_finder` |
| Queue-Suchfilter + `_queue_view`-Index-Mapping | `_render_playlist`, `_play_queue_item`, `move_queue` |
| **Rechtes Panel war 1 px breit** (Pack-Reihenfolge) | `right.pack(before=center)` |
| Mini-Modus versteckt/wiederherstellt rechtes Panel korrekt | `toggle_mini_player` |
| Tk-Styling nach Web-Design-Token | `_build` (Notebook, Entry, Scrollbars …) |
| Web-Playlist: aggregierter Hinweis statt Toast-Spam für lokale Referenzen | `web/app.js` `addPlaylist(Location)` |
| Chromium-Test-Timeout 15→45 s (Last-Flake) | `tests/test_web_browser_runtime.py` |
| README.md in perfektem Englisch | auf Basis des recovered README |
| Klartext-Passwort aus codec-handover.md entfernt | — |

---

## 6. VERIFIKATION (14.08., alle Werte gemessen)

- `pytest -m 'not media'`: **202 passed, 152 deselected** (~7 s)
- GUI-Smoke unter xvfb: **18 passed** (player + converter)
- Interaktiver Voll-Smoke: **16/16 Schritte OK, 0 Fehler** (Start, Add, Play,
  Settings/EPG/Library/URL/YouTube-Dialoge, Resize 900/1400, Mini/Unmini,
  Volume, Mute, Stop, Shutdown)
- Playback >1 s auf allen 4 Backend-Pfaden: MP4→LibVLC (18,6 s), MP3→LibVLC,
  CASU-Sidecar→LegacyCasuBackend, CASUNAT2→NativeCasuBackend
  (frisch gepackt mit `casu pack-v2`, integrity_verified)
- Webplayer E2E (Playwright+Chromium): RADIO.m3u → 24 Kanäle; BASSDRIVE, DLF,
  Byte.FM, FRITZ spielen; Playlist+Datei-Kombination spielt MP3 (3,9 s)
- `RADIO.m3u` (Desktop): `/home/error/Schreibtisch/RADIO.m3u`, 24 Kanäle via `casu.epg.load_m3u`
- DEBs: Build + Install + `dpkg -V` sauber für alle Pakete; installierte
  Dateien byteidentisch mit Repo (`cmp`)
- Nutzer-Session `~/.config/mpcasu/session.json` bereinigt (war testverschmutzt)
- Vom Nutzer bestätigt: **Video-Wiedergabe mit Bild UND Ton** funktioniert.

---

## 7. OFFENE PUNKTE

1. **UX-Wunsch des Nutzers (höchste Priorität):** Desktop-Player
   „Scrollen/Responsivität/Menüführung" verbessern; „aus beiden Playern + alten
   Daten etwas Gutes machen". Beste Basis: Design-System `mpcasu_qt/theme.py`
   + `web/styles.css`-Token; optional PySide6 installieren und `mpcasu_qt` nutzen.
2. Issue #3: FFmpeg-Fallback öffnet externes ffplay-Fenster (sollte einbetten/ablehnen).
3. Chromium-Test flaky unter paralleler Last (einzeln immer grün).
4. 3M-Fuzz-Kampagne vor Final-Release: `python3 tools/fuzz_native_v2.py`.
5. docs/ (Phase 6) auf Redundanzen prüfen.
6. Alte `.casu`-Dateien können defekt sein (Nutzer bestätigt); Player weist
   invalides CASU fail-closed ab (verifiziert).

---

## 8. RETTUNGS-ANLEITUNG FÜR DAS NÄCHSTE TOOL

1. **Dieses Dokument komplett lesen.** Backup-Regeln (Abschnitt 0) befolgen.
2. Backups verifizieren:
   `cd /home/error/Lino-Codec/backups && for d in debs-*; do (cd $d && sha256sum -c SHA256SUMS); done`
   Vollbackup: `sha256sum -c /home/error/Lino-Codec-VOLLBACKUP-2026-08-14.tar.gz.sha256`
3. Tests laufen: `cd /home/error/Lino-Codec && timeout 55 python3 -m pytest -q -m 'not media'`
   (erwartet: 202 passed). GUI: `xvfb-run -a python3 -m pytest tests/test_player_ui.py -q`
4. DEB wiederherstellen (Beispiel Altstand):
   `sudo dpkg -i backups/debs-2026-08-14-0026/*.deb`
5. Code aus DEB extrahieren: `dpkg-deb -x paket.deb ziel/`
6. Weitere Datei-Recovery aus DB falls nötig:
   `python3 artifacts/recovery/db_recovery-script.py`
   (DB: `~/.local/share/opencode/opencode.db` — enthält Inhalte aller je
   geschriebenen/gelesenen Dateien aller Sessions)
7. sudo ist aktuell NOPASSWD. Nichts löschen. Jede Änderung hier dokumentieren.

---

## 9. KONTAKTPUNKTE DES NUTZERS (Kontext für Tonfall/Erwartungen)

- Nutzer ist extrem verärgert über Datenverlust durch frühere opencode-Sessions
  (rm -rf-Vorfall). **Löschaktionen jeder Art sind tabu.**
- Nutzer will: funktionierenden Player (Bild+Ton), schöne UI wie Webplayer,
  alle alten Versionen als Wiederherstellungsquelle verfügbar.
- Nutzer bevorzugt Deutsch. Kurze, konkrete Ergebnisse statt Erklärungen.
