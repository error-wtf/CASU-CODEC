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
- [ ] **STEP-001 (WP-REL-001)** mingw64-Toolchain: cmake/mingw64-toolchain.cmake,
      C++20, warnings, Debug/Release. Gate: Hello-Windows-exe (PE32+,
      `x86_64-w64-mingw32-objdump -p`) + läuft unter Wine.
      *Details: roadmap/tools/release-tools/PORT_ROADMAP.md WP-REL-001*
- [ ] **STEP-002 (WP-REL-002)** Top-Level-CMake modular (casu_core, casu_codec,
      casu_media, casu_network, casu_playback, casu_webapi + Apps) +
      dependencies.cmake + packaging.cmake (CPack zip).
- [ ] **STEP-003 (WP-REL-003)** `scripts/build-windows-release.sh`
      (configure→build→unit→wine→stage→package→sha256→gate), reproduzierbar.
- [ ] **STEP-004 (WP-REL-004 + WP-DEV-000)** DLL/Binary-Audit-Tool
      (`objdump -p` je exe) + gemeinsames Wine-Harness (isoliertes
      WINEPREFIX `.wine-test`, wineboot, xvfb-run, Log-Erfassung).
- [ ] **STEP-005 (WP-REL-007)** Lizenzen: THIRD_PARTY_LICENSES/README-Policy
      anwenden; Textkopien + Versionen/Hashes für Qt/libVLC/FFmpeg/zstd/
      yt-dlp/MinGW-Runtime/SQLite; CASU-Lizenz unverändert.

### A2 Runtime-Beschaffung
- [ ] **STEP-006 (WP-DEP-001..004)** Qt6 (MinGW) + libVLC (Windows) + FFmpeg +
      zstd + SQLite + yt-dlp.exe besorgen/verifizieren; Deployment-Pläne
      (Qt-DLLs + qwindows.dll, vlc/plugins + Discovery, ffmpeg-Helper).
      *Details: research/windows-technology-map.md, ROADMAP M1 E2*

---

# PHASE B — SHARED CORE LIBRARIES (M2)

### B1 casu_core (Format) — details: roadmap/libraries/casu-core/PORT_ROADMAP.md
- [ ] **STEP-007 (WP-CORE-001)** Container-Primitives (Magic/Header, bounded
      I/O, typisierte Fehler, kein Pfad-Traversal).
- [ ] **STEP-008 (WP-CORE-002)** Manifest parse/validate + Limits.
- [ ] **STEP-009 (WP-CORE-003)** CASUNAT1 read/write + payload verify/extract.
- [ ] **STEP-010 (WP-CORE-004)** CASUNAT2 reader (segments).
- [ ] **STEP-011 (WP-CORE-005)** MP5 reader/writer (zstd+zlib, Footer, Attachment).
- [ ] **STEP-012 (WP-CORE-006)** Sidecar resolve + metadata/tiles/scheduler.
- [ ] **STEP-013 (WP-CORE-007)** zstd-Integration (nicht neu implementieren).
- [ ] **STEP-014 (WP-CORE-008)** Golden-Fixtures aus Referenz erzeugen
      (tests/golden; byte vs semantisch pro Format).

### B2 casu_codec / casu_media — details: roadmap/libraries/OTHER_LIBRARIES.md
- [ ] **STEP-015 (WP-CODEC-001..005)** analyze, ffmpeg-Wrapper (QProcess,
      arg-arrays), ffprobe-Wrapper, Presets/Quality, export.
- [ ] **STEP-016 (WP-MEDIA-001..005)** probe, thumbnail, waveform, tags, kind-detect.

### B3 casu_network — details: OTHER_LIBRARIES.md
- [ ] **STEP-017 (WP-NET-001..005)** HTTP-Client, yt-dlp-Wrapper
      (resolve/search/title), spotify, webproviders, Range/206-Primitives.

### B4 casu_playback — details: OTHER_LIBRARIES.md
- [ ] **STEP-018 (WP-PLAY-001..005)** CppPlaybackController, Backend-Interface,
      LibVLCBackend (HWND, events, state 6/7, last_error), NativeCasuBackend,
      Video/AudioSink.

### B5 casu_webapi — details: OTHER_LIBRARIES.md
- [ ] **STEP-019 (WP-WEBAPI-001..005)** Loopback-HTTP + Host-Validation,
      Endpoint-Handler, TranscodeStore, Range/HEAD, Security.

---

# PHASE C — APPS (per Dependency: CLI → Converter → MPCASU → Web-Backend)

### C1 TOOL-CASU-CLI — details: roadmap/tools/casu-cli/PORT_ROADMAP.md
- [ ] **STEP-020 (WP-CLI-000)** CLI-Framework (argparse-Äquivalent in C++).
- [ ] **STEP-021 (WP-CLI-001..015)** jede Subcommand als WP
      (analyze/convert/pack/pack-v2/pack-mp5/mp5-info/native-info/repair-v2/
      export/media/play/validate/verify/info/benchmark) mit Exit-Code-/JSON-Compat.
- [ ] **STEP-022 (WP-CLI-016)** Journal/Resume für convert-Batch.
- [ ] **STEP-023 (WP-CLI-020)** casu.exe ins Paket + Wine-CLI-Vergleich.

### C2 TOOL-CONVERTER — details: roadmap/tools/converter/PORT_ROADMAP.md
- [ ] **STEP-024 (WP-CONV-001..002)** GUI-Foundation + Input/Drag&Drop.
- [ ] **STEP-025 (WP-CONV-010..022)** Probe/Presets/Batch + CASU Import/Export
      + Formate/Metadaten/Thumbnails.
- [ ] **STEP-026 (WP-CONV-030..032)** Progress/Cancel/Fehler/Output/Overwrite/
      Temp-Cleanup.
- [ ] **STEP-027 (WP-CONV-040)** Paket + Wine-GUI.

### C3 TOOL-MPCASU — details: roadmap/tools/mpcasu/PORT_ROADMAP.md + ACCEPTANCE_GATE.md
- [ ] **STEP-028 (WP-MPCASU-001..002)** App-Foundation (Fenster, Single-Instance).
- [ ] **STEP-029 (WP-MPCASU-010..013)** UI-Style (Sidebar/Topbar+NOW PLAYING/
      VideoSurface/Transport+Status+Diagnostics+Cards).
- [ ] **STEP-030 (WP-MPCASU-020..023)** Playback-Core (Controller/Backends/
      Pipeline) — nutzt casu_playback.
- [ ] **STEP-031 (WP-MPCASU-030..035)** Playlist/Library/Settings/EPG/
      Visualizer/DPI/Recording.
- [ ] **STEP-032 (WP-MPCASU-040..042)** YouTube (yt-dlp-Wrapper, Transport,
      Pipeline) — echte YouTube-Wine-Tests.
- [ ] **STEP-033 (WP-MPCASU-050..052)** Webprovider/Input/Shutdown+Errors+Logs.
- [ ] **STEP-034 (WP-MPCASU-060)** Paket + vollständige Wine-Matrix.

### C4 TOOL-WEB-BACKEND — details: roadmap/tools/web-backend/PORT_ROADMAP.md
- [ ] **STEP-035 (WP-WEB-001..004)** HTTP+Security+Static+Range/HEAD.
- [ ] **STEP-036 (WP-WEB-010..017)** API-Endpoints (je ein WP).
- [ ] **STEP-037 (WP-WEB-020..030)** Lifecycle/Shutdown + Paket + Browser↔Backend.

### C5 TOOL-PURE-WEB — details: roadmap/tools/pure-web/PORT_ROADMAP.md
- [ ] **STEP-038 (WP-PURE-001..005)** Frozen verifizieren, byte-identisch nach
      win-release/web/pure kopieren, SHA256-Vergleich, Start-Doku,
      Windows-Browser-Test, Paket-Integration.

---

# PHASE D — PACKAGING + RELEASE (M6)

### D1 Package
- [ ] **STEP-039 (WP-REL-005)** Clean-Wine-Prefix-Paket-Test
      (nur Paket-Inhalt, keine Dev-DLLs/PATH; sonst FAIL).
- [ ] **STEP-040 (WP-REL-006)** `WINDOWS_RELEASE_GATE.json`
      (build/unit/compat/codec/converter/player/youtube/network/web_backend/
      pure_web/packaging/wine/licenses; BLOCKED > fälschlich PASS).
- [ ] **STEP-041 (WP-REL-008)** SHA256 + Reproduzierbarkeit
      (frischer build-windows-release.sh → identisches Paket/Hashes).

### D2 Release-Abschluss
- [ ] **STEP-042** TOOL_PORT_STATUS alle VERIFIED (oder dokumentiert EXCLUDED);
      Feature-Matrix vollständig; `git diff --check` sauber; nur win-release
      geändert; Release-ZIP + SHA256 + Lizenzen + Doku.

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
