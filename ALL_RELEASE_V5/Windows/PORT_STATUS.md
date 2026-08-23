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
| **UI-Parität Struktur** | (2026-08-21, Commit `ac2b7e8`) Side-by-Side-OCR-Vergleich Linux↔Windows: Topbar identisch (‹ Zurück, „Search queue…"-Feld statt Pane-Suche, ☰-Nav-/☷-Queue-Toggle), Statusbar 3-slotig (`MPCASU 3.0.0 \| Optimized… \| CPU/RAM telemetry unavailable`, Transient-Center wie Linux `status()`), Playlist-Pane (PLAYLIST-Titel+Sub, View-Labels All items…Spotify, Shuffle off/on + Repeat off/all/one-Footer), Leerzustand „Drop media here" mit Stage-Routing (leer/Video/Visualizer nach Play-State). **Neu**: Queue-Thumbnails (PPM-Cache via `thumbnail_for`, 54×38-Icons in Video-Zeilen), Per-Media-Preferences (Track+A/V-Delays pro Datei in `.prefs.json`, Apply bei Play, Persist bei Track/Delay/Close), Spotify-URL-Expansion via spotDL-Metadaten in der Sources-Seite. Release Gate PASS, ctest grün, Assets + Notes aktualisiert |
| **CASUNAT2-Stack (§0b Tier 1.1)** | (2026-08-22, Commits `9fb279d` + `e64ed63`) **VOLLSTÄNDIGE BYTE-PARITÄT ZUM PYTHON-REFERENZBAUM ERREICHT**: CASU-0 JSON-Härtung (Duplikat-Keys, Surrogate-Pairs, int64-Overflow fail-closed, `ensure_ascii`-Modus), CASU-1 Tile-Hash mit Python-repr-Kompatibilität (`CASU-STRICT-TILE-v1\0`, Tuple-repr exakt), CASU-2 NativeV2PayloadValidator (feed/finalize, Topologie+Semantik), CASU-3 Writer (kanonische STREAM_CONFIGs, Recovery-Punkte mit checkpoint-Doppeltserialisierung, INTEGRITY_TABLE pts=index_offset, atomar+fsync), CASU-4 Reader (R21/R23-Cross-Checks, offset-keyed Hash-Vergleich, seek_video/reconstruct_video via TileStateCache, recover_native_v2/repair_native_v2). SHA256-Fix: nicht-destruktive Finalisierung (laufende Digest-Snapshots). Tests: `casu_natv2_parity_test` 19/19 — C++-Writer-Ausgabe ist **BYTE-IDENTISCH** mit `casu.native_v2.writer`; Cross-Lesen in beide Richtungen verifiziert |
| **Converter nativ-v2 (CASU-5 + Strict-Decoder)** | (2026-08-22, Commit `e64ed63`) `strict::FrameSource` = Port von casu/strict/decoder.py (30-Format-Tabelle, FFprobe-Inventar, NATIV-pixfmt-Rawvideo-Pipe, `-fps_mode passthrough` für neue FFmpeg-Builds); `convert_media_to_native_v2` = kompletter converter.py-Port (bounded Tags, Cover-Art-Erkennung, s16le-Audio-Pipe synchron zum Inventar, WebVTT-Fallback mit Backtracking-Cue-Parser, ASS-Rich-Attachment, Bitmap-sub2video→FFV1→RGBA-Pfad, Chapter-ns, Font-Rollen, PNG-Cover-Normalisierung) über Streaming-Provider (speichergebunden). **Paritätstest `casu_natv2_convert_test`: C++-Konvertierung ist BYTE-IDENTISCH zur Python-Referenzkonvertierung** auf lossless Fixture (FFV1 gray8 / pcm_s16le / SRT). Wine/Qt-Fix: `waitForFinished`-Quirk bei bereits beendetem Prozess |
| **STRICT-Analyse (ANA-STRICT)** | (2026-08-22, Commit `7c873e2`) iter_state_map-Dreierfenster + valid_until + as_dict-Records **RECORD-IDENTISCH** zur Python-Referenz (120/120 auf Fixture); analyze_strict_video-Struktur komplett; CLI mode=strict produktiv |
| **EPG (Tier 1.3)** | (2026-08-22, Commit `3142918`) casu/epg.py-Vollport: Extended-M3U (tvg-id/-name/group-title/-logo, url-tvg-Listen), XMLTV mit UTC-Offset-Fix (+0200/Z → Guide nicht mehr 2 h versetzt), stop≤start-Filter, Sortierung, Entity-Decoding, Limits (32 MiB/10k/100k), DTD-Ablehnung; MainWindow nutzt echtes tvg-Matching statt Pfad-als-ID; `casu_epg_parity_test` IDENTISCH zur Referenz |
| **Settings (Tier 2.5)** | (2026-08-22, Commit `2d74211`) casu/settings.py-Vollport: Versionhülle {version:1,player:{…}} mit ALLEN 14 Feldern (audio_device neu), exakte Klemmen (rate 0.25–4.0 statt ungebunden, cache [0,65536] statt [64,8192], Split [0,1440], Format-Whitelist), 1-MiB-Lesebound, atomares Schreiben (tmp+fsync+replace) mit json.dumps-kompatibler Serialisierung — **settings.json BYTE-IDENTISCH** zur Referenz; session.json als separate Datei im Linux-Format (Playlist/Current/Position/Geometry WxH+X+Y); `casu_settings_parity_test` ALL PASS |
| **Library (Tier 2.6)** | (2026-08-22, Commit `5daf7c8`) Vollständiges Resume-/Identitätsmodell (size_bytes/modified_ns/resume_seconds/duration_seconds/last_played/last_seen + Tag-Metadata), Bookmarks (Upsert, Default-Label half-even) und gespeicherte Playlists; Extensions-Whitelist **IDENTISCH** zur Referenz (inkl. .casu/.mp5, ohne .m3u/.pls), 100k-Scan-Cap, casefold-Suche/-Gruppierung mit „(unknown)“, A/V-Delays ±5000 ms geklemmt, Prefs atomar; `casu_library_parity_test` 15 Checks ALL PASS |
| **Recording (Tier 2.4)** | (2026-08-22, Commit `2e95e1d`) casu/recording.py-Vollport: Temp-Schreiben + ffprobe-Verifikation + ATOMISCHER Publish (statt Direkt-ins-Ziel), -map_metadata/-map_chapters ergänzt, 10-Container-Whitelist (behebt wirkungsloses record_format), Splitting per record_split_minutes mit part%03d-Rotation und Linux-Stem-Schema, Selbstüberschreibschutz, SIGTERM-255-Fehlnegativ behoben; `casu_recording_parity_test` 10 Checks ALL PASS |
| **Web-Backend (Tier 2.7)** | (2026-08-22, Commit `7bf9194`) web_casu.py-Parität: POST-Mutation-Guard (Sec-Fetch-Site/Origin→403), Radio-Stream-Proxy reaktiviert (ProxyPolicy allow_any_http/https, SSRF-Guard bleibt), kind=video/audio via ffprobe (_media_shape inkl. attached_pic-Skip), Uploads >64 MiB Disk-Spill (kein 16-GiB-RAM-Puffer mehr) via upload_from_file; web_backend/webapi Tests ALL PASS |
| **Visualizer (Tier 2.8)** | (2026-08-22, Commit `9ea8cad`) Dekorativ → REAL: FFT über dekodiertes PCM (casu/waveform.py-Port via viz_fft.hpp), decode_all_pcm-Pipe für Dateien, Live-s16le-Pipe (~40 Hz, 10s-Ring) für Streams, CPU-Drossel (nur sichtbar+spielend); window_wave BIT-IDENTISCH zur Referenz, FFT-Bins ≤2e-5; `casu_viz_parity_test` ALL PASS |
| **Playback (Tier 2.9, Teil 2)** | (2026-08-22, Commit `312cc43`) yt-dlp-Resolve ASYNC mit Generations-Guard (GUI friert nicht mehr ein), ERROR-Diagnose bleibt sichtbar (Latch statt Teardown, last_error_detail in Status+Diagnostics), MP5/CASUNAT1-Temp-Sinks werden getrackt und aufgeräumt; Smoke/Playback/Core ALL PASS |
| **Playback (Tier 2.9, Teil 1)** | (2026-08-22, Commit `717186f`) SAFE_MEDIA_OPTIONS (:avcodec-hw=none pro Media), file://-URI-Reparatur, Resume-dur−5-Klemme, YouTube-Consent-Gate beim Abspielen; Tests ALL PASS. Teil 2 offen: async yt-dlp-Resolve, ERROR-Diagnose, Equalizer, Temp-Sinks, QtVideoSurfaceSink |
| **§0b-Fazit** | Tier 1 KOMPLETT + Tier 2 Items 4–8 KOMPLETT + 9 Teil 1 — **6 neue Paritätstest-Exes, alle ALL PASS**; nur noch Playback-Reste + UI-Politur (Item 10) vor dem v5.0.0-Gate |
| **UI (Tier 2.10, Teil 1–2)** | (`c923b8d`, `aaea380`) right_panel_width 310→370 (Referenzbreite), Esc-Fullscreen-Fix (showNormal), Ctrl+L→SourcesView, Wheel-Volume über Video, A-B-Referenzsemantik (B-vor-A=Fehltoast OHNE A-Reset), snapshot-<stamp>.png |
| Offen | MSVC/QtWebEngine-Endbuild (nur auf echtem Windows); BLOCKER-004 (PATH/Registry auf echtem Windows); BLOCKER-005 (MF/DirectShow-Decoder geplant, nicht gebaut); **§0b-Rest nur noch Tier 2**: Items 4–10 (Recording/Settings/Library/Web-Backend/Visualizer/Playback/UI-Restpunkte) |

## Nächste Schritte (v5.0.0)
1. **§0b-Tierliste weiter abarbeiten** (HARTE REGEL: volle Parität VOR Release):
   ANA-STRICT P2–P5 → EPG-Fixes → Tier 2 (4–10). Reihenfolge + Abnahmekriterien
   siehe `/home/error/HANDOVER.md` §0c Execution Contract.
2. Versionsbump 5.0.0 Assets erst NACH grünem Gesamt-Gate neu bauen.
3. MSVC/QtWebEngine-Endbuild auf Windows-PC (`scripts/build-msvc.bat`) — echter
   eingebetteter Browser (MinGW nutzt WebView2-Pfad, siehe §2 Option B).
4. BLOCKER-004 auf echtem Windows verifizieren (PATH + `.casu`/`.mp5`-Registry).
5. BLOCKER-005: MF/DirectShow-Decoder (CODEC-001) — geplant.
6. Release-Pipeline wie in v3.0.0 (SAFE-GUARD.md Abschnitt 6), dann GitHub-Release.

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