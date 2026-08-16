# MASTER WINDOWS PORT ROADMAP

Stack: **C++20 + Qt 6 + CMake + Ninja + MinGW-w64**, Windows x86_64,
cross-compiled under Linux, verified under Wine. Reference (read-only):
`/home/error/Codec-Casu`. Write area: `win-release/`.

Hierarchy: MILESTONE → EPIC → WORK PACKAGE → TASK.
Status legend: NOT_STARTED / ANALYSIS / IMPLEMENTING / BUILDING / TESTING /
WINE_TESTING / BLOCKED / VERIFIED.

## M1 — FOUNDATION

- **E1 BUILD SYSTEM**
  - WP-BUILD-001 cmake/mingw64-toolchain.cmake (x86_64-w64-mingw32, C++20,
    warnings, Debug/Release/RelWithDebInfo). Deps: none. Gate: empty exe
    builds + `file` shows PE32+.
  - WP-BUILD-002 Top-level CMakeLists with modular targets:
    `casu_core`, `casu_codec`, `casu_media`, `casu_network`, `casu_playback`,
    `casu_webapi`, apps `mpcasu`, `casu_converter`, `casu_web_backend`,
    `casu_cli`. Deps: WP-BUILD-001.
  - WP-BUILD-003 `cmake/dependencies.cmake` + `cmake/packaging.cmake` (CPack
    zip layout). Deps: WP-BUILD-002.
  - WP-BUILD-004 `scripts/build-windows-release.sh` (configure→build→unit→
    wine→stage→package→sha256). Deps: WP-BUILD-003.
- **E2 RUNTIME DEPENDENCIES**
  - WP-DEP-001 Verify/obtain MinGW-w64, cmake, ninja, Qt6 (MinGW), libVLC
    (Windows), FFmpeg, zstd, SQLite, yt-dlp.exe, wine. Record in
    `WINDOWS_RUNTIME_DEPENDENCIES.md`.
  - WP-DEP-002 Qt deployment plan (Qt6Core/Gui/Widgets/Network DLLs +
    `plugins/platforms/qwindows.dll`), `objdump -p` DLL audit helper.
  - WP-DEP-003 libVLC bundle plan (libvlc.dll + plugins dir + discovery).
  - WP-DEP-004 License audit + `THIRD_PARTY_LICENSES/`.

## M2 — CORE (shared libraries)

- **E3 CASU FORMAT (casu_core)**
  - WP-CORE-001 Container primitives (magic/header structs, bounded I/O,
    typed errors). Reference: casu/native.py, casu/mp5/format.py.
  - WP-CORE-002 Manifest parse/validate (schema) + limits.
  - WP-CORE-003 CASUNAT1 read/write + payload verify/extract.
  - WP-CORE-004 CASUNAT2 reader (segments, key-state/tile/PCM chunks).
  - WP-CORE-005 MP5 reader/writer (chunks, zstd+zlib, footer digest,
    attachment extract/verify).
  - WP-CORE-006 Sidecar resolve (source lookup, size+sha256).
  - WP-CORE-007 Golden fixtures (generate from reference; unit + compatibility).
- **E4 CODEC / MEDIA (casu_codec, casu_media)**
  - WP-CODEC-001 ffprobe wrapper (QProcess) → format/streams/duration/tags.
  - WP-CODEC-002 ffmpeg wrapper (transcode/thumbnail/waveform) arg-array safe.
  - WP-CODEC-003 zstd bindings (compress/decompress; corrupt/empty/large).

## M3 — PLAYER

- **E5 PLAYBACK CONTROLLER (casu_playback)**
  - WP-PLAY-001 CppPlaybackController (states + transitions + tests).
- **E6 BACKENDS**
  - WP-PLAY-002 Backend interface (open/play/pause/…/last_error).
  - WP-PLAY-003 LibVLCBackend C++ (RAII instance/media/player, HWND bind,
    events, state mapping 6/7, tracks/chapters/snapshot/rate).
  - WP-PLAY-004 NativeCasuBackend (CASUNAT2 decode, clock/seek/pause,
    WASAPI/Qt audio sink) — see windows-audio-design.md.
- **E7 VIDEO SURFACE / UI**
  - WP-PLAY-005 VideoSurface QWidget (WA_NativeWindow, HWND, no-Qt-overlay
    policy).
  - WP-PLAY-006 MainWindow skeleton + style bible (sidebar/topbar/NOW
    PLAYING/dynamic title/transport/cards) with shared design constants.
  - WP-PLAY-007 Local audio/video playback pipeline (open→controller→surface).
  - WP-PLAY-008 Controls: play/pause/seek/volume/mute/rate/fullscreen/
    snapshot/tracks/subtitles/chapters.
  - WP-PLAY-009 Playlist model + shuffle/repeat/next/prev + M3U/PLS.
  - WP-PLAY-010 Library (SQLite), Settings (portable), Media info dialog.
  - WP-PLAY-011 EPG/IPTV (XMLTV + extended M3U), EPG guide UI.
  - WP-PLAY-012 Visualizer (audio analysis, Qt/QNAM), DPI behavior.
  - WP-PLAY-013 Recording (QProcess/ffmpeg lifecycle).
  - WP-PLAY-014 Drag&drop, keyboard/mouse input map, resize/fullscreen.
  - WP-PLAY-015 Shutdown sequence (processes/sockets/backend/threads).
  - WP-PLAY-016 Error model + logging (libVLC/ffmpeg/yt-dlp/network).
- **E8 YOUTUBE**
  - WP-YT-001 yt-dlp.exe wrapper (QProcess, JSON parse, timeouts).
  - WP-YT-002 Loopback transport (QTcpServer/QNAM: GET/HEAD, Range/206,
    Content-Length/Range, Accept-Ranges, backpressure, loopback+token,
    refresh on 403/410).
  - WP-YT-003 YouTube integration into the normal pipeline (stop-old →
    start-proxy → open → controller). Real-YouTube Wine test required.
- **E9 WEB PROVIDERS**
  - WP-YT-004 Spotify metadata + other webproviders via yt-dlp/HTTP.

## M4 — CONVERTER

- WP-CONV-001 GUI foundation (input select, drag&drop, batch list).
- WP-CONV-002 Probe + source validation (ffprobe).
- WP-CONV-003 Output formats (MP4/MP3/legacy) + CASU import/export.
- WP-CONV-004 Progress/cancel/error/overwrite/output dir.
- WP-CONV-005 Unicode/space/long paths, large files, temp cleanup.

## M5 — WEB (both players)

- **E10 PURE WEB**
  - WP-WEB-001 Copy frozen pure-web release to `web/pure/`; SHA256 compare;
    docs; Windows browser test; packaging integration.
- **E11 WEB BACKEND**
  - WP-WEB-002 Web API contract tests (endpoints/security) from
    `research/web-api-contract.md`.
  - WP-WEB-003 `casu_web_backend` (QTcpServer HTTP + QNAM upstream:
    version, resolve, search, youtube-title, catalog-url, stream-proxy,
    media serve with Range).
  - WP-WEB-004 Frontend `web/` bundled verbatim; browser↔backend integration.
  - WP-WEB-005 Security: loopback-only, host validation, upload/size limits,
    path traversal, malformed ranges.

## M6 — PACKAGING + RELEASE

- WP-PKG-001 `dist/MPCASU-Windows-x86_64.zip` (exes, Qt DLLs, qwindows
  plugin, vlc+plugins, tools/ffmpeg|yt-dlp, web/, licenses, README).
- WP-PKG-002 Clean-Wine-prefix package test (no dev DLLs, no PATH help).
- WP-PKG-003 `WINDOWS_RELEASE_GATE.json` (build/unit/compat/codec/converter/
  player/youtube/network/web_backend/pure_web/packaging/wine/licenses).
- WP-PKG-004 SHA256 + reproducibility (`build-windows-release.sh` fresh run).

## Tests woven into every WP (unit → integration → cross-compile → wine →
compat golden). No WP is VERIFIED without its runtime evidence.
