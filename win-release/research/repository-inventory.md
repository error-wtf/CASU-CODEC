# Repository Inventory (READ-ONLY reference tree: /home/error/Codec-Casu)

Frozen HEAD: `36df249`. Language mix: Python-dominant (≈125 Python files,
7747+ LOC in root modules alone), small HTML/JS/CSS (web + pure-web), shell
(build_debs.sh).

## User-facing applications (entry points)

| Tool ID | Entry point | Kind | Purpose |
|---------|-------------|------|---------|
| TOOL-MPCASU | `python3 -m mpcasu_qt.app` | GUI (PySide6) | Desktop media player |
| TOOL-CONVERTER | `python3 casu_converter.py` | GUI (Tk) | CASU/media converter |
| TOOL-WEB-BACKEND | `python3 web_casu.py` | Web server (Python) | web-casu player backend |
| TOOL-PURE-WEB | `pure-web-release/index.html` | Static web | backend-free player (frozen) |
| TOOL-CASU-CLI | `python3 -m casu` | CLI | CASU command line |
| TOOL-LEGACY-PLAYER | `python3 mpcasu_player.py` | GUI (legacy) | old player UI |

## Libraries / modules (shared logic)

- `casu/` — core: codec, container (CASUNAT1/NAT2/legacy), MP5, manifest,
  checksums, segments, metadata, scheduling, EPG, playlist, library, settings,
  search, spotify, webproviders, transcode, thumbnail, waveform, tags, tiles,
  recording, probe, export.
- `mpcasu_backend.py` — LibVLCBackend (ctypes→libVLC C API), LegacyCasuBackend.
- `mpcasu_native_backend.py` — NativeCasuBackend (native decode + sinks).
- `mpcasu_playback.py` — PlaybackController state machine.
- `mpcasu_qt/` — Qt UI (MainWindow ~217KB, VideoSurface, web player tabs,
  theme), `app.py` entry.
- `mpcasu_web/` — small legacy web player (index.html, player.js).
- `web/` — web-casu frontend (app.js, casu-native.js, index.html, styles.css).

## Developer / diagnostic tools (`tools/`, 16 scripts)

smoke_qt_*, smoke_web_*, smoke_backends, smoke_owner_casu, smoke_session4,
acceptance_qt, acceptance_web, screenshot_cli/converter/qt/web,
fuzz_native_v2, release_gate_guard.

## External tools / dependencies used by the reference

- yt-dlp (YouTube resolve/search/titles) — invoked via subprocess.
- ffmpeg/ffprobe (probe, transcode, thumbnail, waveform, recording) — subprocess.
- libVLC (shared library, ctypes) — playback of legacy/network media.
- PulseAudio (Linux audio sink for native CASU).
- zstd (CASU compression, via Python bindings).
- SQLite (library DB).
- Qt/PySide6 (GUI, QtWebEngine for web players).

## Entry points summary for Windows port

| Reference | Windows target |
|-----------|----------------|
| `python3 -m mpcasu_qt.app` | `MPCASU.exe` (Qt6 C++) |
| `python3 casu_converter.py` | `CASU-Converter.exe` (Qt6 C++) |
| `python3 web_casu.py` | `CASU-Web-Backend.exe` (Qt6 native HTTP) |
| `pure-web-release/` | `web/pure/` bundled as-is (byte-identical) |
| `python3 -m casu` | `casu.exe` (C++ CLI) |
| `tools/*.py` | Windows test/diagnostic equivalents where useful |

## Linux-specific constructs to replace (initial scan)

- PulseAudio (`PulseAudioSink`) → Windows audio (WASAPI/Qt Multimedia).
- `VLC_PLUGIN_PATH` / `/usr/lib/.../vlc/plugins` → bundled VLC plugins dir.
- X11 `winId()`/`set_xwindow` → `HWND`/`libvlc_media_player_set_hwnd`.
- POSIX paths, `/tmp`, executable discovery → QStandardPaths/std::filesystem.
- subprocess/Popen → QProcess (arg arrays, no shell strings).
- urllib → QNetworkAccessManager.
