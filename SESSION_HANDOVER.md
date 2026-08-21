# SESSION HANDOVER — Playlist-Gruppen-Semantik (nicht-destruktiv) — alle Player

## 1. Repository State

```text
repository root : /home/error/Codec-Casu
current branch  : main
HEAD commit     : edb51f1 (gepusht; danach folgen die uncommitteten Änderungen)
git status      : M ALL_RELEASE_V5/** (README, FEATURE_MATRIX, PORT_STATUS,
                    RUN_CHECKLIST, SAFE-GUARD, START_HIER — Linux + Windows)
                  M casu/playlist.py
                  M mpcasu_qt/main_window.py
                  M tests/test_playlist.py
                  M tests/test_queue_playback_behavior.py
                  M tools/smoke_web_playlist.py (erweitert: Gruppen-Tools,
                    Block-Move, Mehrfachauswahl, rein/raus, Save-selection)
                  M web/app.js  M web/styles.css        (web-casu Backend-Player)
                  M pure-web-release/app.js  M pure-web-release/styles.css
                  M win-release/web/pure/*               (byte-identisch)
                  M win-release/apps/mpcasu/main_window.{cpp,hpp}
                  M win-release/apps/mpcasu/playlist.{cpp,hpp}
                  M win-release/tests/casu_playlist_test.cpp
                  M dist/MPCASU-PURE-WEB-3.0.0.zip       (neu, SHA 6d6d7bf8…)
                  M dist/SHA256SUMS
```

WICHTIG: Inhaltlich FERTIG + verifiziert (Linux 432 passed, Windows ctest 14/14
unter Wine, Web Node-Harness + Playwright-Smoke grün, DEBs installiert,
acceptance_web 16/16). Es fehlen: **Commit + Push + GitHub-Release-Assets**
(Schritt 5 unten) + ggf. Nutzer-Repro-Test.

Neueste Commits (abwärts):
- `edb51f1` playlist: fix queue/playlist playback on both platforms + rebuild release
- `ce16b9f` fix: mpcasu launcher runs installed package always + QtWebEngine sandbox for root/containers
- `6804b40` release-planning: ALL_RELEASE_V5 (Windows/Linux/macOS/Android) + versioning policy (skip v4, next v5.0.0)

## 2. Current Product / Version State

```text
current Linux version/build   : v3.0.0 (Python/PySide6 Player, mpcasu_qt/; DEBs 3.0.0
                                neu gebaut 2026-08-20, installiert, web/ byte-identisch)
current Windows version/build : v3.0.0 (C++20/Qt6/MinGW, win-release/apps/mpcasu,
                                NSIS setup.exe; Windows-Release-Build läuft/nachzuholen)
current web players           : web/ (Backend-Player via web_casu.py, im casu-codec-DEB)
                                + pure-web-release/ (Quelle des MPCASU-PURE-WEB-3.0.0.zip,
                                SHA 6d6d7bf8…, 18 Dateien; win-release/web/pure byte-identisch)
currently installed Linux     : DEBs 3.0.0 aus dist/ (2026-08-20) — web/app.js + styles.css
                                byte-identisch zu Repo (sha256sum), mpcasu startet als root
currently installed Windows   : WINEPREFIX=/tmp/opencode/wine-prefix (ctest 14/14);
                                altes Setup v3.0.0 installiert — NEUER Build (mit
                                Gruppen-Semantik + neuem pure web) steht noch aus
release dirs                  : dist/ (DEBs + SHA256SUMS + MPCASU-PURE-WEB-3.0.0.zip),
                                win-release/dist/ (ZIP, setup.exe, Gate, SHA256SUMS)
```

Zukunfts-Entwicklung: **v4.x wird übersprungen, nächste Version v5.0.0**
(siehe RELEASE_POLICY.md, ALL_RELEASE_V5/).

## 3. Design — Nicht-destruktive Gruppen-Queue (VERBINDLICH alle Player)

- Playlist-Gruppen bleiben im Queue als sichtbare Zeile (nie aufgelöst);
  Wiedergabe läuft über die **logische Sequenz** der flachen Einträge.
- Linux: `_play_seq`/`_invalidate_play_seq` (main_window.py), Model bleibt flach.
- Windows: `logical_sequence()` + `seq_valid_`/`invalidate_seq()` (main_window.hpp
  inline); Playlist-Pane ist QTreeWidget mit Gruppenzeilen + Platzhalter-Kind,
  `expand_playlist_group`/`refresh_playlist_group` laden Kinder lazy.
- Web (web-casu + Pure Web): flaches `state.items` mit `item.playlist`-Attribut;
  Gruppen = UI/Attribut (EPG/IPTV-Views iterieren flach). `moveRowSegment`
  Bounds-Check VOR dem Splice (nie Item-Verlust). Kein persistQueue im
  Backend-Player (web/app.js); Pure Web hat persistQueue/restoreQueue (playlist
  bleibt erhalten).
- Features überall: Gruppen-Tools (▶ spielen, ↑/↓, ×), Kontextmenü
  (Expand/Collapse, Move, Remove, "Remove ALL entries from playlist (keep in
  queue)"), Mehrfachauswahl Strg/Shift + Block-Move (move_many), Einsortieren
  ("Save selection to playlist…"/"Move to playlist…", dedupliziert),
  Aussortieren ("Remove from playlist" → bleibt lose), Batch-Dedup
  (Playlist + eigene Dateien; Re-Add einer geladenen Playlist wird übersprungen).
- **Dauerhafte Markierung (Nutzer-Complaint behoben):** Die Markierung
  überlebt Verschieben und Entfernen — nur überlebende Zeilen bleiben markiert,
  Esc/leere Auswahl löscht. Linux: `PlaylistPane.select_rows()` +
  `populate(..., selected=list)`, `_on_playlist_move`/`_on_playlist_remove`
  speichern Pfade vor dem Re-Render und wählen danach wieder an. Windows:
  `reselect_playlist_rows()` (QTreeWidgetItem::setSelected — QTreeWidget hat
  in Qt6 KEIN setItemSelected!), move_playlist_rows + remove-Button
  (keep-Survivors). Web: `state.multi` wird in removeRows/removePlaylistGroup
  auf Überlebende gefiltert, movePlaylistGroup löscht nicht mehr;
  Queue-Summary zeigt "N marked (Esc clears)", Esc-Keydown räumt.

## 4. Verifikation (alles grün, Stand 2026-08-20)

```text
Linux  : QT_QPA_PLATFORM=offscreen QTWEBENGINE_DISABLE_SANDBOX=1
         /usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider
         → 433 passed, 12 skipped (inkl. test_queue_playback_behavior,
           move_many, test_marking_survives_move_and_removal)
Windows: Build grün; ctest unter Wine 14/14 (OHNE casu_playback_vlc_test +
         casu_playback_youtube_live_test — kein Audio-Gerät/kein Live-Netz)
         WINEPREFIX=/tmp/opencode/wine-prefix WINEDEBUG=-all
         ctest --test-dir build-win64 -j2   (Log /tmp/opencode/win_ctest.log)
         casu_playlist_test.exe: 41 Checks ALL PASS, EXIT=0
Web    : node --check web/app.js pure-web-release/app.js
         node /tmp/opencode/pureweb_queue_test.js   (25 Checks ALL PASS,
           inkl. Markierung überlebt moveRows/removeRows/Gruppen-Move, Esc)
         node /tmp/opencode/webapp_queue_test.js    (19 Checks ALL PASS)
         python3 tools/smoke_web_playlist.py        (inkl. Persistenz-Check
           nach #move-up, mehrfach grün)
         python3 tools/acceptance_web.py            → 16/16 (installiertes web-casu)
Pakete : DEBs 3.0.0 neu gebaut + installiert (web/ byte-identisch verifiziert)
         dist/MPCASU-PURE-WEB-3.0.0.zip (SHA 6d6d7bf8…), SHA256SUMS neu
```

## 5. Next Steps (NUR noch Release-Abschluss)

```text
1. Windows-Release NEU bauen (main_window.cpp geändert — Markierungs-Persistenz):
   cd win-release && SKIP_WINE=1 ./scripts/build-windows-release.sh
   → Log /tmp/opencode/win_release_build.log; danach release_gate.sh laufen
   lassen (Gate 14/14, player NOT_TESTED) + WINDOWS_RELEASE_GATE.json prüfen.
2. git add + commit (alle Dateien aus §1) + push
   Remote: error-wtf/CASU-CODEC, Branch main, Token: /home/error/gittoken.env
   (export GH_TOKEN="$(head -1 /home/error/gittoken.env)")
3. GitHub-Release v3.0.0-Assets NEU hochladen (--clobber) — DEBs/Web/Zip sind
   durch die Markierungs-Fixes veraltet:
   - dist/mpcasu_3.0.0_all.deb, dist/casu-codec_3.0.0_all.deb,
     dist/MPCASU-PURE-WEB-3.0.0.zip, dist/SHA256SUMS
   - win-release/dist/MPCASU-Windows-x86_64.zip, MPCASU-Setup-3.0.0.exe, SHA256SUMS
   Danach IMMER kombinierte SHA256SUMS neu berechnen + hochladen
   (Ablauf: HANDOVER.md §4 Schritt 4).
4. Nutzer-Repro-Test (Complaint): Markieren → ↑/↓ mehrfach verschieben ohne
   erneutes Markieren → Entfernen (Überlebende bleiben markiert) → Esc.
   Web: http://127.0.0.1:8497/web/ → Queue-Summary "N marked (Esc clears)".
   Pure Web: Loopback-Host für YouTube, siehe win-release/README_WINDOWS.md.
```

## 6. Key Source Files (aktueller Stand)

**Linux:**
- `mpcasu_qt/main_window.py` — `_play_seq`, `_invalidate_play_seq`,
  `play_next/play_previous` (logische Sequenz), PlaylistPane (Gruppenzeilen,
  Mehrfachauswahl, move_many/remove_many, Save/Move to playlist, Remove from
  playlist), `add_files` Batch-Dedup.
- `casu/playlist.py` — `is_playlist`, `remove_many`, `move_many`.
- `tests/test_queue_playback_behavior.py` + `tests/test_playlist.py` — 433 total.

**Windows:**
- `win-release/apps/mpcasu/main_window.{cpp,hpp}` — QTreeWidget-Playlist-Pane,
  `logical_sequence`, `play_queue_index`/`play_seq_entry`, Gruppen-Kontextmenü,
  `move_playlist_rows`, `merge_selection_into_playlist`,
  `remove_children_from_playlist`, `move_children_to_playlist`, Batch-Dedup.
- `win-release/tests/casu_playlist_test.cpp` — Gruppen-Semantik (41 Checks).

**Web:**
- `web/app.js` + `styles.css` — Backend-Player (minified; `$` =
  `document.querySelector` mit `#id`-Selektoren; KEIN persistQueue).
- `pure-web-release/app.js` + `styles.css` — Pure Web (kanonische Zip-Quelle;
  persistQueue erhält `playlist`-Attribut).
- `tools/smoke_web_playlist.py` — Playwright-Smoke (erweitert 2026-08-20).
- Test-Harnesses: `/tmp/opencode/webapp_queue_test.js`,
  `/tmp/opencode/pureweb_queue_test.js`.

## 7. Files / Directories to Ignore

- `win-release/dist/_stage/`, Golden-Kits, Recovery-Packs
- `HANDOVER.md` (alte Notizen vom 19.08. — Release-/Upload-Ablauf dort gültig,
  insb. `gh release upload --clobber`)
- `mpcasu_web/` (Legacy-Player, nicht ausgeliefert)
- alte Audits/Matrizen (nur Architektur-Kontext)
# SESSION HANDOVER 2026-08-20 — UI-Parität Windows ↔ Linux (21 Lücken) + Release v3.0.0 neu

## 8. Was gemacht wurde
- **Audit „identischer Aufbau und Funktionen":** alle 21 UI/Feature-Lücken im
  Windows-Player `win-release/apps/mpcasu/main_window.cpp` geschlossen
  (DiagnosticsBar, Drop-Overlay, Toast+Screen-Clamp, Queue-Rename,
  Rec-Settings-Dialog, Options-Cache-Leeren+Provider-Status, Shuffle-`[on]`,
  Live-Persistenz Volume/Mute/Rate, Badges-Spalte, Now-Playing-EPG,
  YouTube-Suche+Consent-Gate+Playlist-Expand, Tag-Titel, EPG-Karten-Grid,
  Media-Info CASU-Manifest, Library-Vollausbau, Chapters/Tracks/Device-Menüs,
  A/V-Delays, externes Untertitel, Frame-Step, Visualizer-Linux-Optik).
- Backend: `libvlc_bind.h` + `LibVLCBackend` um VLC-3.0-API erweitert
  (set_chapter, next_frame, audio/video delay, add_slave, audio device list);
  `casu_playback_test.cpp` MockBackend-Stubs ergänzt (Abstract-Klasse).
- Fix: `--play-test` überspringt Session-Restore (Konstruktor-Parameter
  `bool play_test`), damit CI nie alte Sessions (Radio.m3u) lädt.
- Release-Pipeline `scripts/build-windows-release.sh` grün (Gates 14/14,
  ctest 16/16 unter Wine, DLL-Audit 22 OK, NSIS-Setup). Installation unter
  Wine verifiziert (Program Files, `casu` im PATH, Smoke-Clean-Exit).
- Screenshot `/tmp/opencode/shots/mpcasu_nowplaying.png` (1360×820).

## 9. Offen
- Commit+Push dieser Änderungen; GitHub-Release-Assets hochladen (Token
  `/home/error/gittoken.env`, `gh release upload --clobber`); v5.0.0-Versionsbump.
- MSVC/QtWebEngine-Endbuild nur auf echtem Windows; BLOCKER-004/005 offen.

## 10. Nachfolge-Fixes 2026-08-21 (v3.0.0 neu)
- **Kritischer Navigations-Bug:** `navigate()`-Index-Map zeigte bei mehreren Seiten
  die falsche QStackedWidget-Seite (Build-Reihenfolge ≠ Map). Folge: „WEB PLAYERS"
  (Spotify/HearThis/Tidal/Netflix/Browse) schien zu fehlen — eigentlich wurde
  YOUTUBE angezeigt. Map auf tatsächliche Build-Reihenfolge korrigiert; per
  `--page`-Screenshot unter Wine für alle Seiten verifiziert.
- **Playlist-Formate:** `PlaylistModel` parst jetzt WPL/XSPF/JSPF/ASX/RMP/RAM/
  MPCASU-JSON zusätzlich zu M3U/PLS (vorher nur M3U/PLS) — `playlist.cpp`.
  `casu_playlist_test` erweitert (XSPF/WPL/JSPF/JSON/ASX/RAM, ALL PASS).
- Testflag `--page <Name>` + `MainWindow::navigate_to()` (Screenshot-Verifikation).
- Release-Pipeline grün (ctest 16/16, Gate 14/14), installiert unter Wine,
  Web-Tabs im installierten Paket nachgewiesen.

## 2026-08-21 (II) — Windows: volle UI-Parität mit Linux-Referenz (Commit ac2b7e8)

Vorgehen: PySide6 installiert → Linux-App unter xvfb gestartet + Screenshot;
Windows-Screenshot unter Wine; OCR-/Pixel-/Geometrie-Vergleich beider Apps.

Strukturelle Fixes:
- Topbar = Linux: ‹ Zurück, NOW PLAYING + Titel, „Search queue…"-Feld (aus dem
  Pane in den Topbar verschoben), ☰ Nav-Toggle, ☷ Queue-Toggle.
- Statusbar = Linux 3 Slots (Version | Tagline | Telemetry); `status()` schreibt
  ins Center-Slot; „N item(s) in queue" entfernt (existiert in Linux nicht).
- Playlist-Pane: PLAYLIST-Titel+Sub, View-Labels (All items…Spotify),
  Shuffle/Repeat-Footer (Semantik wie Linux: Text spiegelt Zustand).
- Leerzustand „Drop media here" (Radial-Gradient, Icon, Meta) als Stage-Index 2;
  `update_stage()` routet leer/Video/Visualizer nach Play-State
  (`stage_media_active_`); Stop → leer.

Neue Features (Parität):
- Queue-Thumbnails: `request_queue_thumbnails()`/`apply_thumb()` — Video-Zeilen
  (.mp4/.mkv/.webm/.mov/.avi) bekommen PPM-Cache-Thumbnails (54×38,
  KeepAspectRatioByExpanding) via `casu::media::thumbnail_for`; verifiziert
  (Cache-Dateien + sichtbare Icons im Screenshot).
- Per-Media-Preferences: `PlaybackPreferences` in library.hpp/cpp (separate
  `<lib>.prefs.json`), `apply_media_preferences()` nach Backend-Open,
  `persist_media_preferences()` bei Track-Wahl/Delay-Dialog/closeEvent.
  Hinweis: C++-Backend-Delays geben void zurück (anders als Python).
- Spotify-URLs werden in `on_youtube_play` via `casu::network::expand_spotify`
  zu abspielbaren Zeilen expandiert (Linux `_expand_spotify_url`).

Verifikation: ctest grün (youtube_live flaky→Rerun ok), Release Gate PASS,
Wine-Install-Smoke ok, Web-Tabs + Playback per Screenshot bestätigt.
Assets auf v3.0.0 neu hochgeladen (--clobber, 10 Dateien), Release-Notes
„Update 2026-08-21 (II)" angehängt. PORT_STATUS.md Zeile „UI-Parität Struktur".
