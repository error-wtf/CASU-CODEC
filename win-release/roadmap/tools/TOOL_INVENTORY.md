# Tool Inventory (Windows port)

Every standalone tool/entry point found in the frozen reference tree, with
its Windows target. Shared logic is factored into libraries, never duplicated
per tool.

| Tool ID | Name | Entry (reference) | Kind | Windows artifact | Priority |
|---------|------|-------------------|------|------------------|----------|
| TOOL-MPCASU | MPCASU Qt Player | `python3 -m mpcasu_qt.app` | GUI | `MPCASU.exe` | CRITICAL |
| TOOL-CONVERTER | CASU Converter | `python3 casu_converter.py` | GUI | `CASU-Converter.exe` | HIGH |
| TOOL-WEB-BACKEND | web-casu backend | `python3 web_casu.py` | server | `CASU-Web-Backend.exe` | HIGH |
| TOOL-PURE-WEB | Pure web player | `pure-web-release/` | static web | `web/pure/` (bundled, byte-identical) | HIGH (integration) |
| TOOL-CASU-CLI | CASU CLI | `python3 -m casu` | CLI | `casu.exe` | MEDIUM |
| TOOL-LEGACY-PLAYER | Legacy player | `python3 mpcasu_player.py` | GUI | `casu-legacy.exe` (optional) | LOW |
| TOOL-SMOKE-QT | Qt smokes | `tools/smoke_qt_*` | dev | Windows test/diag versions | MEDIUM |
| TOOL-SMOKE-WEB | web smokes | `tools/smoke_web_*` | dev | reuse where meaningful | MEDIUM |
| TOOL-SCREENSHOT | screenshot helpers | `tools/screenshot_*` | dev | reuse for Wine UI gates | MEDIUM |
| TOOL-FUZZ | native v2 fuzz | `tools/fuzz_native_v2.py` | dev | port as C++ fuzz test | LOW |
| TOOL-RELEASE-GUARD | release gate guard | `tools/release_gate_guard.py` | dev | port to Windows gate | MEDIUM |

## Shared libraries (to build once, link everywhere)

- `casu_core` — CASU format: container, manifest, checksums, segments, MP5,
  native CASUNAT1/NAT2, zstd, metadata.
- `casu_codec` — codec logic (uses FFmpeg libav / ffmpeg helper).
- `casu_media` — probe, thumbnail, waveform, tags.
- `casu_network` — http client (QNetworkAccessManager), URL handling,
  web providers, Spotify matching.
- `casu_playback` — PlaybackController state machine + backend interfaces
  (LibVLCBackend, NativeCasuBackend).
- `casu_webapi` — web-casu API contract implementation (Qt HTTP server).

## Dependencies (Windows runtime)

| Dep | Role | Decision |
|-----|------|----------|
| Qt 6 (Core/Gui/Widgets/Network) | GUI + net | bundle DLLs + qwindows plugin |
| libVLC | playback | bundle libvlc.dll + plugins |
| FFmpeg (ffmpeg.exe/ffprobe.exe) | probe/transcode/thumbnail | bundle as helpers (QProcess) |
| yt-dlp.exe | YouTube resolve/search | bundle as helper (QProcess) |
| zstd | CASU compression | bundle native lib |
| SQLite | library DB | Qt SQL or sqlite3 |
| MinGW runtime | runtime | bundle mingw DLLs |

## Ordering principle

1. Shared CASU core (format/codec) first — everything depends on it.
2. Playback foundation (controller + LibVLCBackend + VideoSurface/HWND).
3. MPCASU local playback → audio → controls → playlist/library.
4. Converter.
5. YouTube transport.
6. Web backend + pure-web integration.
7. Packaging + Wine regression.

See `roadmap/EXECUTION_PLAN.md` and per-tool `roadmap/tools/<id>/`.
