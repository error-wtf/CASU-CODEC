# PORT_STATUS — Windows (ALL_RELEASE_V5)

| Field | Value |
|-------|-------|
| Current version | **v3.0.0 veröffentlicht** (GitHub-Release v3.0.0) |
| Next version | **v5.0.0** (v4.x übersprungen) |
| Reference tree modified | NO |
| Baseline | HEAD `2367dcbc`, 400 tests PASS (Linux-Referenz) |
| Pure Web Release | 3.0.0 frozen (SHA `b71b5d0b…`) → **neu 2026-08-20** (Gruppen-Semantik, SHA `6d6d7bf8…`, 18 Dateien) |
| ctest (Wine) | **16/16 grün** inkl. `mpcasu_smoke_test` (Smoke + Play-Test) und `casu_playlist_test` |
| Release-Gate | **14/14 PASS** — `win-release/dist/WINDOWS_RELEASE_GATE.json` (generated_utc 2026-08-20T21:10:38Z) |
| Golden | 8 PASS (verify_golden.sh) |
| Installer | setup.exe gebaut + install/uninstall unter Wine verifiziert (PATH bleibt) |
| Playlist-Queue | **Gruppen-Semantik** vollständig auf Windows portiert (QTreeWidget, logische Sequenz, Gruppen + Mehrfachauswahl verschiebbar, ein-/aussortierbar, Batch-Dedup) — Tests ALL PASS; Build grün; `web/pure` byte-identisch aktualisiert |
| **UI-Parität** | **Alle 21 Audit-Lücken geschlossen** (2026-08-20): DiagnosticsBar, Drop-Overlay, Toast+Screen-Clamp, Queue-Rename, Rec-Settings-Dialog, Cache-Leeren + Provider-Status, Shuffle-`[on=true]`, Live-Volume/Mute/Rate-Persistenz, Badges-Spalte, Now-Playing-EPG-Zeile, YouTube-Suche + Consent-Gate + Playlist-Expand, Tag-Titel, EPG-Karten-Grid (M3U/URL/Play), Media-Info CASU-Manifest, Library-Vollausbau (Suche/Modi/Favoriten/Ordner/Scan), Chapters-, Track-, Device-Menüs, A/V-Delays, externes Untertitel, Frame-Step, Visualizer-Linux-Optik. Backend: `set_chapter`/`next_frame`/Delays/`add_slave`/Device-Liste in `libvlc_bind.h` + `LibVLCBackend`. Fix: Play-Test ignoriert Session-Restore (`--play-test`). Release neu gebaut + installiert (Program Files, PATH ✓, Smoke ✓) |
| **Navigation-Fix + Web-Tabs** | (2026-08-21) Seiten-Index-Map in `navigate()` korrigiert (WEB PLAYERS/LIBRARY/YOUTUBE/EPG/SETTINGS/ABOUT zeigten zuvor die falsche Seite — Ursache „fehlende" Web-Player-Tabs). Jetzt per `--page`-Screenshot unter Wine verifiziert: SPOTIFY/HEARTHIS/TIDAL/NETFLIX/BROWSE-Tabs erscheinen. Alle Seiten navigieren korrekt |
| **Playlist-Formate** | `PlaylistModel` parst jetzt vollständig M3U/M3U8, PLS, WPL, XSPF, JSPF, ASX/WMX/WVX, RMP/RAM und MPCASU-JSON (vorher nur M3U/PLS) — `casu_playlist_test` um XSPF/WPL/JSPF/JSON/ASX/RAM erweitert (ALL PASS) |
| Offen | MSVC/QtWebEngine-Endbuild (nur auf echtem Windows); BLOCKER-004 (PATH/Registry auf echtem Windows); BLOCKER-005 (MF/DirectShow-Decoder geplant, nicht gebaut) |

## Nächste Schritte (v5.0.0)
1. Versionsbump 3.0.0 → 5.0.0 überall (setup.nsi, Paketversion, Doku).
2. MSVC/QtWebEngine-Endbuild auf Windows-PC (`scripts/build-msvc.bat`) — echter
   eingebetteter Browser (MinGW = Stub).
3. BLOCKER-004 auf echtem Windows verifizieren (PATH + `.casu`/`.mp5`-Registry).
4. BLOCKER-005: MF/DirectShow-Decoder (CODEC-001) — geplant.
5. Release-Pipeline wie in v3.0.0 (SAFE-GUARD.md Abschnitt 6), dann GitHub-Release.

## Verlauf (v3.0.0)
- Phase A Foundation, B Shared-Core, C Apps, D Packaging+Gate — alle VERIFIED.
- Web-Provider-Tabs (QtWebEngine-Pfad, CASU_HAVE_WEBENGINE) + setup.exe ergänzt.
- Playlist-Queue-Feature (Playlist-Play + Merge) auf Windows portiert + Tests.

## Verlauf (v3.0.0-Nachfolger / Gruppen-Semantik)
- Windows-Player auf nicht-destruktive Gruppen-Queue umgestellt: Playlist-Pane
  ist jetzt ein QTreeWidget (Gruppenzeilen, auf-/zuklappbar, ↑/↓/×/Load/Save
  mit Mehrfachauswahl), Wiedergabe läuft über die logische Sequenz
  (`logical_sequence()`, Repeat-One/Shuffle erhalten), Kontextmenü mit
  Play/Expand/Collapse/Save selection/Move to playlist/Remove from playlist,
  `add_files` mit Batch-Dedup, `move_playlist_rows`/`move_children_to_playlist`/
  `remove_children_from_playlist` neu. Alle `casu_playlist_test`-Checks ALL PASS.
- **Web-Player** (web-casu `/web/` + Pure Web `pure-web-release/`): gleiche
  Gruppen-Semantik implementiert (Gruppen-Tools, Kontextmenü, Mehrfachauswahl
  Block-Move, rein/raus, Re-Add-Dedup) — Node-Unit-Harness ALL PASS (17 + 12
  Checks) + Playwright-Smoke `tools/smoke_web_playlist.py` mehrfach grün;
  `MPCASU-PURE-WEB-3.0.0.zip` neu erzeugt (18 Dateien, SHA `6d6d7bf8…`),
  `win-release/web/pure/` byte-identisch aktualisiert.