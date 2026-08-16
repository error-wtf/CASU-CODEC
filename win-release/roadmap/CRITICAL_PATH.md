# CRITICAL PATH + RISK REGISTER + EXECUTION PLAN

## Critical path (what blocks everything else)

```
Toolchain (mingw-w64 + cmake + ninja)        [WP-BUILD-001]
   ↓
Qt 6 runtime + deployment plan               [WP-DEP-001/002]
   ↓
Shared casu_core (container/manifest)        [WP-CORE-001..007]
   ↓
casu_playback (controller + backend iface)   [WP-PLAY-001/002]
   ↓
LibVLCBackend + VideoSurface (HWND)          [WP-PLAY-003/005]
   ↓
Local playback pipeline                      [WP-PLAY-007]
   ↓
Everything else (converter/web/YouTube/packaging)
```

First stable milestone: **empty Windows GUI that builds and runs under Wine**
(Foundation + MainWindow skeleton), then local MP4 playback. No big-bang.

## Risk register

| ID | Risk | Level | Mitigation | Test | Fallback |
|----|------|-------|-----------|------|----------|
| R1 | MinGW/Qt ABI mismatch (MSVC vs MinGW binaries) | CRITICAL | Use MinGW Qt build; verify `file`/`objdump`; no mixing | build gate | switch Qt build |
| R2 | libVLC plugins not found (libvlc.dll alone insufficient) | CRITICAL | Bundle `vlc/plugins`, set discovery env, dir next to exe | clean-prefix run | list plugin path in diagnostics |
| R3 | HWND embedding (surface lifetime, resize, fullscreen) | HIGH | WA_NativeWindow; keep handle valid; resize policy; no Qt overlay on video | Wine video tests | fallback to offscreen surface? (documented) |
| R4 | Native CASU audio on Windows (no PulseAudio) | HIGH | WASAPI/Qt sink, explicit design doc | Wine audio | libVLC fallback |
| R5 | Qt DLL deployment incomplete (qwindows.dll) | HIGH | Controlled deployment + objdump audit | clean prefix | windeployqt-style script |
| R6 | YouTube transport (Range/206, refresh, CDN) | MEDIUM | Port proven proxy logic; unit + fake upstream + real CDN | real YouTube Wine run | degrade with clear error |
| R7 | FFmpeg/yt-dlp path/arg safety (spaces/Unicode) | MEDIUM | QProcess arg arrays; never shell strings | Unicode path tests | – |
| R8 | DPI scaling breaks layout | MEDIUM | Logical pixels, Qt scaling, screenshot gates | 100–200% | per-DPI tuning |
| R9 | Thread lifecycle (workers, proxy, web server shutdown) | MEDIUM | Ownership doc; clean shutdown sequence | leak/exit tests | – |
| R10 | Wine ≠ Windows (fake positives) | MEDIUM | Always also logical code review; note Wine quirks; don’t code Wine-specific fixes as universal | – | – |
| R11 | Feature loss during port | HIGH | Feature matrix + per-tool audits; BLOCKED not deleted | matrix check | – |
| R12 | Repo write-boundary violation | HIGH | Session-start audit; only win-release writes | `git status --short` | revert |

## Execution plan (order of work)

```
STEP 001  WP-BUILD-001  mingw64 toolchain + hello exe → Wine run
STEP 002  WP-BUILD-002  modular CMake targets skeleton
STEP 003  WP-DEP-001..004  deps + Qt/libVLC/FFmpeg bundle + licenses
STEP 004  WP-CORE-001..007  casu_core (golden fixtures from reference)
STEP 005  WP-PLAY-001..002  controller + backend interface (unit)
STEP 006  WP-PLAY-003      LibVLCBackend (HWND) → Wine MP4
STEP 007  WP-PLAY-005/006  VideoSurface + MainWindow skeleton → Wine GUI
STEP 008  WP-PLAY-007/008  local playback pipeline + controls
STEP 009  WP-PLAY-009..016  playlist/library/settings/EPG/viz/recording/… 
STEP 010  WP-YT-001..003  YouTube (resolver+proxy+libVLC) real test
STEP 011  WP-CONV-001..005  converter
STEP 012  WP-WEB-001..005  pure-web bundle + web backend
STEP 013  WP-PKG-001..004  packaging, clean prefix, gate, sha256
```

Each STEP: reference re-read → implement → cross-compile → unit → wine →
compat → VERIFIED → next. Update `PORT_STATUS.md` after each step.
