# WINDOWS PORT BASELINE

This document freezes the reference state of the CASU-CODEC repository that
the Windows port is built against. The reference tree is **READ ONLY**.

| Field | Value |
|-------|-------|
| Repository | https://github.com/error-wtf/CASU-CODEC |
| Working tree | /home/error/Codec-Casu |
| Git SHA (HEAD) | `36df249ed90089e35137a798fda87cbfb43fafa8` |
| Branch | `main` |
| Date | 2026-08-16 |
| Tests (reference) | **400 passed, 12 skipped** (offscreen Qt, python3.14) |
| Pure Web Release | `MPCASU-PURE-WEB-2.0.0.zip`, SHA256 `64143894217b34d23571535848210c0ad871a19a5d8730d7782234966fa2e754` |
| GitHub Release | `v2.0.0` (debs + SHA256SUMS + Pure Web zip) |
| Write area (Windows port) | /home/error/Codec-Casu/win-release |

> **This source tree is the frozen reference implementation for the Windows
> port and must not be modified by the Windows migration.**

## Existing components (frozen)

| Component | Location | Language | Role |
|-----------|----------|----------|------|
| CASU core/container/codec | `casu/` (core, schema, fileio, filetypes, mp5, native, native_v2, strict, tiles, tags, scheduler) | Python | codec, formats |
| CASU converter | `casu_converter.py` | Python/Tk | GUI converter |
| MPCASU Qt player | `mpcasu_qt/` (app.py, main_window.py, videoframe.py, webplayers.py, theme.py) | Python/PySide6 | desktop player |
| Player backend | `mpcasu_backend.py` (LibVLCBackend via ctypes) | Python/ctypes | playback |
| Native CASU backend | `mpcasu_native_backend.py` | Python | native decode |
| Playback controller | `mpcasu_playback.py` | Python | state machine |
| Legacy player | `mpcasu_player.py` | Python | legacy UI |
| web-casu backend | `web_casu.py` | Python | web player server |
| web-casu frontend | `web/` (index.html, app.js, casu-native.js, styles.css) | HTML/JS/CSS | web player |
| Pure web player | `pure-web-release/` (frozen, released as ZIP) | HTML/JS/CSS | backend-free web player |
| Legacy codec ref | `legacy_ssc_codec_v01.py` | Python | historical reference |
| `casu/cli.py` | `casu/__main__.py` | Python | CLI |
| Developer tools | `tools/` (16 scripts: smoke_*, acceptance_*, screenshot_*, fuzz, release_gate_guard) | Python | dev/diagnostics |
| Packaging | `packaging/build_debs.sh` | Bash | Linux debs |
| Tests | `tests/` | Python/pytest | reference tests |

## Reference semantics

- **CASU format** is the primary container (CASUNAT1/CASUNAT2/legacy, MP5).
- **MPCASU** = single native player: PlaybackController → Backend (LibVLC /
  NativeCasu) → VideoSurface. No second player, no browser fallback for
  desktop playback.
- **YouTube** = yt-dlp resolver → optional loopback byte/range transport →
  LibVLCBackend → PlaybackController → VideoSurface.
- **web-casu** = separate web product (browser <video>), backend Python server.
- **pure-web** = backend-free web player (frozen, released).
- The Linux/Web code is the **specification, test oracle and design
  reference** for the Windows port.

## Porting scope (decided)

- Target: **C++20 + Qt 6 + CMake + Ninja + MinGW-w64**, Windows x86_64,
  cross-compiled under Linux, verified under Wine.
- yt-dlp / ffmpeg are NOT reimplemented; used as bundled helpers (QProcess).
- libVLC is used via its C API (in-process), never an external vlc.exe.
- Desktop apps: MPCASU, CASU-Converter. Web: pure (bundled as-is) + backend
  (native Windows implementation of the web-casu API).
- Everything in this repository outside `win-release/` stays untouched.
