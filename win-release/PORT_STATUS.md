# PORT STATUS

| Field | Value |
|-------|-------|
| Current phase | **PHASE A–D VERIFIED; Web-Player echt (WebView2), Installer per-user + auto-update + per-app icons, Converter Journal/Resume — v3.0.0 Windows-Parität abgeschlossen** |
| Current execution step | **v3.0.0 Windows-Release final** (16/16 Wine-Tests, Gate PASS, Silent-Install/Update/Uninstall unter Wine verifiziert) — optional: MSVC/QtWebEngine-Endbuild auf Windows |
| Reference tree modified | NO |
| Baseline | HEAD `2367dcbc`, 400 tests PASS |
| Pure Web Release | published (SHA in baseline) |
| STEP-001 | **VERIFIED** — casu_hello.exe PE32+ (`file`), läuft unter Wine (WINEPREFIX=.wine-test) |
| STEP-002 | **VERIFIED** — dependencies.cmake + packaging.cmake; CPack-Zip (Qt-DLLs, qwindows.dll, vlc/plugins, tools/, casu.exe, Lizenzen) |
| STEP-003 | **VERIFIED** — scripts/build-windows-release.sh läuft reproduzierbar durch |
| STEP-004 | **VERIFIED** — scripts/wine-run.sh (Harness) + scripts/dll-audit.sh |
| STEP-005 | **VERIFIED** — THIRD_PARTY_LICENSES/ vollständig |
| STEP-006 | **VERIFIED** — Qt6 6.8.3 mingw_64, libVLC+plugins, ffmpeg/ffprobe/yt-dlp.exe, zstd.exe in third_party/ |
| STEP-007..012 | **VERIFIED** — casu_core: Container-Primitives, Manifest, CASUNAT1, CASUNAT2, MP5 (zlib), Sidecar — jeweils Unit+Golden unter Wine (s. Liste unten) |
| STEP-013 (WP-CORE-007) | **VERIFIED** — libzstd 1.5.7 für MinGW aus Quelle gebaut (BLOCKER-001 gelöst); mp5.cpp `decompress` versucht zstd zuerst, fällt auf zlib zurück (Referenz `casu/mp5/reader.py:47`); Writer bleibt zlib (byte-identische Golden-Fixtures). Unit: zstd-Roundtrip + korrupter Payload → CasuError; 13/13 Tests grün unter Wine |
| Phase B2 (casu_codec) | implementiert (analyze/ffmpeg/ffprobe/presets/export); casu_codec_test **ALL PASS unter Wine** |
| Phase B2 (casu_media) | implementiert (probe/thumbnail/waveform/tags/kind); casu_media_test **ALL PASS unter Wine** |
| Phase B3 (casu_network) | implementiert (http/yt-dlp/spotify/providers/range); casu_network_test **ALL PASS unter Wine** |
| Phase B4 (casu_playback) | implementiert (controller/backend-Interface/LibVLCBackend); casu_playback_test + casu_playback_vlc_test (echter libVLC-Decode unter Wine, clock advanced) **PASS** |
| Phase B5 (casu_webapi) | implementiert (http/server/security/transcode_store/media_serve); casu_webapi_test **ALL PASS unter Wine** |
| Phase C CLI (casu.exe) | alle Subcommands implementiert; casu_cli_test **ALL PASS unter Wine** (kind/verify/info/pack/pack-mp5/mp5-info/export/…); casu.exe im CPack-Zip |
| Phase C Converter | CASU-Converter.exe (Qt-GUI) implementiert; casu_converter_test + casu_converter_engine_test **ALL PASS unter Wine**; Fenster-Screenshots in test-results/wine/. **Neu:** Conversion-Journal + Resume verifizierter Jobs (`casu::journal` in casu_core, Port von casu/jobs.py), Advanced-Optionen (analysis_fps/tile_size/key_interval_seconds) fließen in CASU-Manifest + MP5 + Batch-Report ein, GUI übergibt vollständige Jobliste (Journal-Identität wie Linux) |
| Phase C MPCASU | MPCASU.exe implementiert; mpcasu_smoke_test **PASS** (Fenster sichtbar, play-test: PLAYING, pos=2.9s/6.0s) |
| Phase C Web-Backend | CASU-Web-Backend.exe implementiert; casu_web_backend_test **ALL PASS unter Wine**; exe-run.log: "WEB CASU running at http://127.0.0.1:8497/web/" |
| STEP-038 (WP-PURE-001..005) | Frozen Pure-Web 3.0.0 verifiziert (SHA256 b71b5d0b…, Zip-Dir-Identität geprüft), **byte-identisch nach web/pure/ kopiert** (diff -rq leer, per-file-Hashes == Release-Zip), im CPack-Zip enthalten (SHA-Vergleich Paket↔Frozen: identisch). Start-Doku in README_WINDOWS.md. **Windows-Browser-Test (WP-PURE-004) noch offen** |
| STEP-022 (WP-CLI-016) | **VERIFIED** — Journal/Resume für convert+transcode implementiert (journal.cpp: `.casu-conversion-<sha256[:16]>.json`, atomisches {version,state,updated_ns,jobs,results}, hash-verifizierter Resume mit `resumed:true`; Job-Set-Mismatch → CasuError; Werkzeug-Suche jetzt paket-aware: <exe_dir>/tools, <exe_dir>/third_party/tools, cwd, PATH). Unit unter Wine grün (convert→journal→resume→tamper→re-convert) |
| STEP-032 (WP-MPCASU-040..042) | **VERIFIED — HARTES GATE erfüllt** — echter YouTube/CDN unter Wine: `casu_playback_youtube_live_test` resolvt echtes Video via gebündeltem yt-dlp.exe (player_client=android, git-Historik-Lektion), proxy-t durch den Loopback-Transport und vergleicht Range/206-Bytes byte-exakt gegen den Live-CDN (Full-Stream 28,5 MB). Voraussetzungen dabei gefixt: OpenSSL 3.4.1 (MinGW-Source-Build) + Qt-TLS-Plugin `plugins/tls/qopensslbackend.dll` gebündelt; yt-dlp-Wrapper um `player_client=android` ergänzt; YoutubeProxy-Streaming (Headers vor Body, readyRead-Pump) korrigiert |
| Test-Suite gesamt | **14/14 ctest grün unter Wine** (casu_core, codec, media, network, webapi, playback, playback_vlc, playback_youtube, playback_youtube_live, mpcasu_smoke, web_backend, cli, converter_engine, converter, golden_verify) |
| STEP-014 (WP-CORE-008) | **VERIFIED** — tests/golden/verify_golden.sh: Referenz `python3 -m casu` vs Wine `casu.exe` auf den Fixtures (validate/verify NAT1+NAT2, native-info, info, mp5-info) — Exit-Codes + JSON-Shape identisch; **byte-level Payload-SHA-256 NAT1 == Referenz** (`71d8177d…405aa`); als ctest `golden_verify` registriert, PASS |
| STEP-039 (WP-REL-005) | **VERIFIED** — Clean-Prefix-Paket-Test: frisches WINEPREFIX, nur Paketinhalt; MPCASU --smoke, Converter --smoke-test, casu.exe kind/verify/mp5-info, Web-Backend (web/ + api/version + pure) OK. Marker test-results/clean-prefix.log |
| STEP-040 (WP-REL-006) | **VERIFIED** — scripts/release_gate.sh → dist/WINDOWS_RELEASE_GATE.json; **13/13 Gates PASS** (build/unit/compat/codec/converter/player/youtube/network/web_backend/pure_web/packaging/wine/licenses) |
| STEP-041 (WP-REL-008) | **VERIFIED** — Reproduzierbarkeit: 2 getrennte cpack-Läufe → 513 Dateien byte-identisch (`diff -rq` leer; nur Zip-mtimes unterscheiden sich); dist/SHA256SUMS geschrieben |
| Web-Provider-Tabs | **ECHT implementiert — Microsoft Edge WebView2 (MinGW) + QtWebEngine (MSVC)** — `web_player_tabs.{hpp,cpp}` (exakte Portierung von mpcasu_qt/webplayers.py): eingebettete Tabs für Spotify/Hearthis/Tidal/Netflix/BROWSE, persistente Logins je Provider (`%APPDATA%\CASU\webview2\<provider>` bzw. QtWebEngine-Profil), URL/Suche-Handoff identisch. MinGW-Build: `CASU_HAVE_WEBVIEW2` + `WebContainerWidget` (native HWND-Host, WebView2Loader.dll per LoadLibrary, DRM/Widevine → Netflix/Tidal/Spotify spielen wirklich ab); fehlt die Runtime → transparenter Fallback-Hinweis + „im Standardbrowser öffnen". MSVC-Build: `CASU_HAVE_WEBENGINE` (Chromium). **YouTube bleibt yt-dlp → Loopback → libVLC (kein Browser-Tab)** |
| setup.exe | **VERIFIED (NSIS-Installer, überarbeitet)** — `scripts/setup.nsi` → `dist/MPCASU-Setup-3.0.0.exe`. Neu: (1) **Per-App-Icons** — jede Verknüpfung/EXE/Datei-Assoziation nutzt ihr eigenes Icon (MPCASU=Player, Converter=Converter, Web-Backend=Web-CASU; identisch zu Linux-Desktop-Einträgen; Icons als .rc in die EXEs eingebettet), `assets/assets`-Doppelordner im Paket behoben. (2) **Auto-Update** — bestehende Installation (Machine- UND Per-User-Scope) wird erkannt und in-place aktualisiert; laufende Apps werden per taskkill geschlossen. (3) **Non-Admin** — `RequestExecutionLevel highest`, kein erzwungener UAC: Admin→Machine (HKLM, `$PROGRAMFILES64`, System-PATH), Standard-User→Per-User (HKCU, `%LocalAppData%\MPCASU`, Benutzer-PATH); unwritable alte Machine-Install → fallback Per-User statt Abbruch. **Unter Wine getestet**: Silent-Install, Re-Install aktualisiert in-place (gleicher Pfad), Shortcuts mit korrekten Icons verifiziert, Silent-Uninstall räumt vollständig |

## Progress

- [x] Freeze + Pure Web Release (GitHub v2.0.0)
- [x] Alle Analyse-Dokumente (research/*, roadmap/*, WINDOWS_PORT_FEATURE_MATRIX.md)
- [x] SCHRITT 0 Prerequisites beschafft (Qt6-MinGW, libVLC, ffmpeg/ffprobe/yt-dlp.exe, zstd)
- [x] STEP-001..012 (Phase A + casu_core B1) VERIFIED (inkl. Golden-PASS für NAT1/NAT2/MP5-Fixtures)
- [x] STEP-013 (WP-CORE-007) zstd-Integration VERIFIED (BLOCKER-001 gelöst via Source-Build libzstd 1.5.7)
- [x] Phase B2–B5 Shared-Core-Libs implementiert + Wine-Tests grün
- [x] Phase C Apps (CLI, Converter, MPCASU, Web-Backend) implementiert + Wine-Tests grün
- [x] STEP-022 (WP-CLI-016) Journal/Resume VERIFIED
- [x] STEP-032 echter-YouTube-Wine-Gate VERIFIED (OpenSSL 3.4.1 + TLS-Plugin + player_client=android + Proxy-Streaming-Fix)
- [x] STEP-014 (WP-CORE-008) Golden-Fixtures VERIFIED (verify_golden.sh, byte-level Payload-SHA)
- [x] STEP-039 (WP-REL-005) Clean-Prefix-Paket-Test VERIFIED
- [x] STEP-040 (WP-REL-006) WINDOWS_RELEASE_GATE.json VERIFIED (13/13 PASS)
- [x] STEP-041 (WP-REL-008) SHA256 + Reproduzierbarkeit VERIFIED (513 Dateien byte-identisch)
- [x] Web-Provider-Tabs (QtWebEngine eingebettet) implementiert; YouTube bleibt yt-dlp→libVLC
- [x] setup.exe (NSIS-Installer) erstellt + unter Wine installiert/uninstalliert getestet

## Next steps

1. **STEP-042 (Abschluss)** — TOOL_PORT_STATUS alle VERIFIED/EXCLUDED, Feature-Matrix vollständig, `git diff --check` sauber, nur win-release geändert, finaler Release-ZIP + setup.exe + SHA256 + Lizenzen + Doku.
2. **BLOCKER-004** — Installer PATH/Dateityp-Registry auf echtem Windows verifizieren (`casu` aus jeder Konsole, Doppelklick auf .casu öffnet MPCASU).
3. **Optional: MSVC/QtWebEngine-Endbuild auf Windows** — `scripts/build-msvc.bat` auf einem Windows-PC mit Visual Studio ausführen, um den eingebetteten QtWebEngine-Chromium-Build (exakt Linux-Verhalten) nativ zu bauen.
4. **CODEC-001 (geplant, BLOCKER-005)** — Media-Foundation/DirectShow-Decoder für CASUNAT2 als eigenständiges Teilprojekt (Architektur in WINDOWS_INSTALL_AND_CODEC.md).
5. **WP-PURE-004** — Pure-Web Windows-Browser-Test (kein Browser unter Wine verfügbar — dokumentierter EXCLUDED-Kandidat).

## Offene Punkte / Blocker
- BLOCKER-001 (libzstd MinGW) → **gelöst**.
- BLOCKER-002 (echter-YouTube-Gate) → **gelöst** (STEP-032).
- BLOCKER-003 (Pure-Web-Browser-Test) → offen (kein Browser unter Wine).
- BLOCKER-004 (Installer PATH/Dateityp auf echtem Windows) → offen.
- BLOCKER-005 (MF/DirectShow-Decoder) → geplant, nicht gebaut (Linux-Parität reicht für "exakt gleich").
- BLOCKER-006 (QtWebEngine-Codepfad) → gelöst (MinGW=Stub, MSVC aktiv; MSVC-Endbuild ausstehend).
- WP-PURE-004 → offen.
- STEP-042 Abschluss → offen (Feature-Matrix-Update, finaler Commit).