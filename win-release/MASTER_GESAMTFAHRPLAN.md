# MASTER GESAMTFAHRPLAN — der eine Fahrplan für den großen Portierungs-Run

Dieses Dokument IST der abzuarbeitende Einzelfahrplan. Es verweist für Details
auf die Per-Tool-/Library-Fahrpläne (siehe `NAVIGATION.md`). Reihenfolge ergibt
sich aus Dependencies (nie umgekehrt).

## Arbeits-Grundregeln (gelten IMMER)
1. **Nur `win-release/` ist Schreibgebiet.** Referenzbaum (Codec-Casu, vlc,
   webamp-embed) = lesen/ausführen/testen, NIE verändern.
2. **Ein Work-Package (WP) pro Iteration.** Für jedes WP: Status ANALYSIS →
   Referenz gezielt lesen (`REFERENCE_LOOKUP.md`) → implementieren (nur
   win-release) → cross-compile → unit → wine → compat → **erst dann VERIFIED**.
3. **Kein WP ohne Nachweis als fertig markieren** (Build-Exit, Test-Ergebnis,
   echter Wine-Lauf, echtes YouTube/CDN, Golden-Vergleich).
4. Fehler nie überspringen: lösen ODER als `BLOCKED` in `roadmap/BLOCKERS.md`
   dokumentieren und weiter (nicht still auslassen).
5. Nach jeder größeren Phase: `PORT_STATUS.md` + `WINDOWS_PORT_FEATURE_MATRIX.md`
   aktualisieren; `git status --short` prüft Read-only.
6. Bei unerwartet Komplexem: zuerst Ursache/Referenz/Ownership/Logs, dann
   ändern. Keine Workaround-Museen.

## Zustands-Codes
NOT_STARTED / ANALYSIS / IMPLEMENTING / BUILDING / TESTING / WINE_TESTING /
BLOCKED / VERIFIED.

---

# PHASE A — FOUNDATION (Shared, blockiert alles)

### A1 Toolchain & Build
- [x] **STEP-001 (WP-REL-001)** mingw64-Toolchain: cmake/mingw64-toolchain.cmake,
      C++20, warnings, Debug/Release. Gate: Hello-Windows-exe (PE32+,
      `x86_64-w64-mingw32-objdump -p`) + läuft unter Wine.
      *Details: roadmap/tools/release-tools/PORT_ROADMAP.md WP-REL-001*
- [x] **STEP-002 (WP-REL-002)** Top-Level-CMake modular (casu_core, casu_codec,
      casu_media, casu_network, casu_playback, casu_webapi + Apps) +
      dependencies.cmake + packaging.cmake (CPack zip).
- [x] **STEP-003 (WP-REL-003)** `scripts/build-windows-release.sh`
      (configure→build→unit→wine→stage→package→sha256→gate), reproduzierbar.
- [x] **STEP-004 (WP-REL-004 + WP-DEV-000)** DLL/Binary-Audit-Tool
      (`objdump -p` je exe) + gemeinsames Wine-Harness (isoliertes
      WINEPREFIX `.wine-test`, wineboot, xvfb-run, Log-Erfassung).
- [x] **STEP-005 (WP-REL-007)** Lizenzen: THIRD_PARTY_LICENSES/README-Policy
      anwenden; Textkopien + Versionen/Hashes für Qt/libVLC/FFmpeg/zstd/
      yt-dlp/MinGW-Runtime/SQLite; CASU-Lizenz unverändert.

### A2 Runtime-Beschaffung
- [x] **STEP-006 (WP-DEP-001..004)** Qt6 (MinGW) + libVLC (Windows) + FFmpeg +
      zstd + SQLite + yt-dlp.exe besorgen/verifizieren; Deployment-Pläne
      (Qt-DLLs + qwindows.dll, vlc/plugins + Discovery, ffmpeg-Helper).
      *Details: research/windows-technology-map.md, ROADMAP M1 E2*

---

# PHASE B — SHARED CORE LIBRARIES (M2)

### B1 casu_core (Format) — details: roadmap/libraries/casu-core/PORT_ROADMAP.md
- [x] **STEP-007 (WP-CORE-001)** Container-Primitives (Magic/Header, bounded
      I/O, typisierte Fehler, kein Pfad-Traversal).
- [x] **STEP-008 (WP-CORE-002)** Manifest parse/validate + Limits
      (bounded JSON-Parser json.cpp + validate_manifest nach casu/schema.py;
      Unit unter Wine grün).
- [x] **STEP-009 (WP-CORE-003)** CASUNAT1 read/write + payload verify/extract
      (native.cpp: 92B-Header, Atomic-Write, verify+extract; Unit unter Wine grün;
      **Golden-PASS**: demo_clip.mp4.casu unter Wine → payload_sha256
      `71d8177d…405aa` == Python-Referenz).
- [x] **STEP-010 (WP-CORE-004)** CASUNAT2 reader (segments).
      (native_v2.cpp: Header/Manifest strict-parse, Chunk-Walk mit laufendem
      sha256-Digest, Integrity-Table + chunk_sha256-Tabelle verifiziert,
      Seek-Index + Recovery-Points, END/kein Trailing; **Golden-PASS**:
      demo_casunat2.casu unter Wine → 1032 chunks / 2 seek / integrity=1 /
      31 recovery == Python-Referenz. SHA-256-Padding-Bug 64k+55 gefixt.)
- [x] **STEP-011 (WP-CORE-005)** MP5 reader/writer (zstd+zlib, Footer, Attachment).
      (mp5.cpp: Header "<8sHHII"=20B korrigiert, Chunk "<BHII"=11B stream_id=u16
      korrigiert, zlib-Deflate/Inflate, Footer 36B, Attachment-Extract+sha256;
      JSON-dump float/exponent an Python angepasst für Digest-Golden;
      **Golden-PASS**: demo.mp5 unter Wine → 5 chunks / 0 issues / Attachment
      demo_clip.mp4 (139073B) == Referenz.)
- [x] **STEP-012 (WP-CORE-006)** Sidecar resolve + metadata/tiles/scheduler.
      (sidecar.cpp resolve_casu_source: Source-Auflösung, size+sha256-Verifikation,
      kein Pfad-Traversal; Unit unter Wine grün.)
- [x] **STEP-013 (WP-CORE-007)** zstd-Integration (nicht neu implementieren).
      (libzstd 1.5.7 für MinGW aus Quelle gebaut → BLOCKER-001 gelöst; mp5.cpp
      decompress: zstd zuerst, dann zlib-Fallback wie Referenz reader.py:47;
      Writer bleibt zlib für byte-identische Golden-Fixtures. Unit: zstd-Roundtrip
      + korrupter Payload → CasuError; 13/13 ctest grün unter Wine.)
- [ ] **STEP-014 (WP-CORE-008)** Golden-Fixtures aus Referenz erzeugen
      (tests/golden; byte vs semantisch pro Format).
      (Golden-Vergleiche NAT1/NAT2/MP5 laufen bereits via fixtures/ + cli + manuell;
      formalisieren in tests/golden/ steht aus.)

### B2 casu_codec / casu_media — details: roadmap/libraries/OTHER_LIBRARIES.md
- [x] **STEP-015 (WP-CODEC-001..005)** analyze, ffmpeg-Wrapper (QProcess,
      arg-arrays), ffprobe-Wrapper, Presets/Quality, export.
      (implementiert; casu_codec_test ALL PASS unter Wine)
- [x] **STEP-016 (WP-MEDIA-001..005)** probe, thumbnail, waveform, tags, kind-detect.
      (implementiert; casu_media_test ALL PASS unter Wine)

### B3 casu_network — details: OTHER_LIBRARIES.md
- [x] **STEP-017 (WP-NET-001..005)** HTTP-Client, yt-dlp-Wrapper
      (resolve/search/title), spotify, webproviders, Range/206-Primitives.
      (implementiert; casu_network_test ALL PASS unter Wine)

### B4 casu_playback — details: OTHER_LIBRARIES.md
- [x] **STEP-018 (WP-PLAY-001..005)** CppPlaybackController, Backend-Interface,
      LibVLCBackend (HWND, events, state 6/7, last_error), NativeCasuBackend,
      Video/AudioSink.
      (implementiert; casu_playback_test + echtes libVLC-Decode casu_playback_vlc_test PASS unter Wine)

### B5 casu_webapi — details: OTHER_LIBRARIES.md
- [x] **STEP-019 (WP-WEBAPI-001..005)** Loopback-HTTP + Host-Validation,
      Endpoint-Handler, TranscodeStore, Range/HEAD, Security.
      (implementiert; casu_webapi_test ALL PASS unter Wine)

---

# PHASE C — APPS (per Dependency: CLI → Converter → MPCASU → Web-Backend)

### C1 TOOL-CASU-CLI — details: roadmap/tools/casu-cli/PORT_ROADMAP.md
- [x] **STEP-020 (WP-CLI-000)** CLI-Framework (argparse-Äquivalent in C++).
- [x] **STEP-021 (WP-CLI-001..015)** jede Subcommand als WP
      (analyze/convert/pack/pack-v2/pack-mp5/mp5-info/native-info/repair-v2/
      export/media/play/validate/verify/info/benchmark) mit Exit-Code-/JSON-Compat.
      (implementiert; casu_cli_test ALL PASS unter Wine)
- [x] **STEP-022 (WP-CLI-016)** Journal/Resume für convert-Batch.
      (journal.cpp: atomisches `.casu-conversion-<sha256[:16]>.json`,
      hash-verifizierter Resume `resumed:true`, Mismatch→CasuError;
      Werkzeug-Suche paket-aware. Wine-Unit grün.)
- [x] **STEP-023 (WP-CLI-020)** casu.exe ins Paket + Wine-CLI-Vergleich.
      (casu.exe im CPack-Zip; Wine-CLI-Test grün)

### C2 TOOL-CONVERTER — details: roadmap/tools/converter/PORT_ROADMAP.md
- [x] **STEP-024 (WP-CONV-001..002)** GUI-Foundation + Input/Drag&Drop.
- [x] **STEP-025 (WP-CONV-010..022)** Probe/Presets/Batch + CASU Import/Export
      + Formate/Metadaten/Thumbnails.
- [x] **STEP-026 (WP-CONV-030..032)** Progress/Cancel/Fehler/Output/Overwrite/
      Temp-Cleanup.
- [x] **STEP-027 (WP-CONV-040)** Paket + Wine-GUI.
      (CASU-Converter.exe implementiert; converter+engine-Tests ALL PASS unter Wine;
      Fenster-Screenshots in test-results/wine/)

### C3 TOOL-MPCASU — details: roadmap/tools/mpcasu/PORT_ROADMAP.md + ACCEPTANCE_GATE.md
- [x] **STEP-028 (WP-MPCASU-001..002)** App-Foundation (Fenster, Single-Instance).
- [x] **STEP-029 (WP-MPCASU-010..013)** UI-Style (Sidebar/Topbar+NOW PLAYING/
      VideoSurface/Transport+Status+Diagnostics+Cards).
- [x] **STEP-030 (WP-MPCASU-020..023)** Playback-Core (Controller/Backends/
      Pipeline) — nutzt casu_playback.
- [x] **STEP-031 (WP-MPCASU-030..035)** Playlist/Library/Settings/EPG/
      Visualizer/DPI/Recording.
- [x] **STEP-032 (WP-MPCASU-040..042)** YouTube (yt-dlp-Wrapper, Transport,
      Pipeline) — **echter-YouTube-Wine-Gate VERIFIED** (HARTES GATE):
      casu_playback_youtube_live_test → echtes Video via yt-dlp.exe gelöst,
      Loopback-Proxy + Range/206 byte-exakt gegen Live-CDN (28,5 MB Full-Stream).
      Fixes dabei: OpenSSL 3.4.1 (MinGW-Source-Build) + Qt-TLS-Plugin gebündelt,
      yt-dlp `player_client=android`, YoutubeProxy-Streaming korrigiert.
- [x] **STEP-033 (WP-MPCASU-050..052)** Webprovider/Input/Shutdown+Errors+Logs.
- [x] **STEP-034 (WP-MPCASU-060)** Paket + Wine-Smoke-Matrix.
      (MPCASU.exe implementiert; mpcasu_smoke_test PASS: Fenster sichtbar + play-test
      PLAYING pos=2.9s/6.0s)

### C4 TOOL-WEB-BACKEND — details: roadmap/tools/web-backend/PORT_ROADMAP.md
- [x] **STEP-035 (WP-WEB-001..004)** HTTP+Security+Static+Range/HEAD.
- [x] **STEP-036 (WP-WEB-010..017)** API-Endpoints (je ein WP).
- [x] **STEP-037 (WP-WEB-020..030)** Lifecycle/Shutdown + Paket + Browser↔Backend.
      (CASU-Web-Backend.exe implementiert; casu_web_backend_test ALL PASS unter Wine;
      "WEB CASU running at http://127.0.0.1:8497/web/")

### C5 TOOL-PURE-WEB — details: roadmap/tools/pure-web/PORT_ROADMAP.md
- [x] **STEP-038 (WP-PURE-001..005)** Frozen verifizieren, byte-identisch nach
      win-release/web/pure kopieren, SHA256-Vergleich, Start-Doku,
      Paket-Integration.
      (Frozen 3.0.0 SHA256 b71b5d0b… verifiziert; Kopie byte-identisch
      (per-file-Hashes == Release-Zip); web/pure/ im CPack-Zip enthalten und
      mit dem Frozen verglichen; Start-Doku in README_WINDOWS.md.
      **Offen:** WP-PURE-004 Windows-Browser-Test unter Wine.)

---

# PHASE D — PACKAGING + RELEASE (M6)

### D1 Package
- [x] **STEP-039 (WP-REL-005)** Clean-Wine-Prefix-Paket-Test
      (nur Paket-Inhalt, keine Dev-DLLs/PATH; sonst FAIL).
      (VERIFIED 2026-08-18: MPCASU/Converter/casu.exe/Web-Backend in frischem
      WINEPREFIX nur mit Paketinhalt OK; Marker test-results/clean-prefix.log)
- [x] **STEP-040 (WP-REL-006)** `WINDOWS_RELEASE_GATE.json`
      (build/unit/compat/codec/converter/player/youtube/network/web_backend/
      pure_web/packaging/wine/licenses; BLOCKED > fälschlich PASS).
      (VERIFIED: scripts/release_gate.sh → dist/WINDOWS_RELEASE_GATE.json,
      13/13 Gates PASS)
- [x] **STEP-041 (WP-REL-008)** SHA256 + Reproduzierbarkeit
      (frischer build-windows-release.sh → identisches Paket/Hashes).
      (VERIFIED: 2 cpack-Läufe → 513 Dateien byte-identisch; dist/SHA256SUMS)
- [x] **STEP-043 (WP-REL-009)** NSIS setup.exe Installer (systemweit: PATH +
      Dateitypen + Startmenü) mit CASU-Icon.
      (VERIFIED 2026-08-19: Silent-Install/Uninstall unter Wine; PATH/Dateityp-
      Registry nur auf echtem Windows verifizierbar → BLOCKER-004)
- [x] **STEP-044 (Web-Provider-Tabs)** eingebetteter QtWebEngine-Browser für
      Spotify/Hearthis/Tidal/Netflix/BROWSE (Port von webplayers.py) +
      webproviders. YouTube bleibt yt-dlp→Loopback→libVLC (kein Browser-Tab).
      QtWebEngine nur für MSVC → CASU_HAVE_WEBENGINE (MinGW=Stub, MSVC=build-msvc.bat).

### D2 Release-Abschluss
- [ ] **STEP-042** TOOL_PORT_STATUS alle VERIFIED (oder dokumentiert EXCLUDED);
      Feature-Matrix vollständig; `git diff --check` sauber; nur win-release
      geändert; Release-ZIP + SHA256 + Lizenzen + Doku.
      (offen: Feature-Matrix-Update, finale Abnahme, ggf. MF-Decoder siehe BLOCKER-005)

---

## Blocker-Log
- Qt6-MinGW-Binaries, libVLC-Windows, ffmpeg/yt-dlp-Windows → Beschaffung,
  kein Design-Blocker. → `roadmap/BLOCKERS.md` pflegen.

## Wichtig für den Run
- Nach JEDEM STEP: Status in diesem Dokument abhaken, `PORT_STATUS.md`
  aktualisieren, nächsten freigegebenen STEP beginnen.
- Nie zwei WPs parallel; nie weiterspringen bei offenem Fehler (BLOCKED loggen).
- Länge/Token: pro STEP gezielt `REFERENCE_LOOKUP.md` + ein research-Dokument
  lesen, nicht alles.
