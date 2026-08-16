# MPCASU — Windows Port Roadmap (Tool: TOOL-MPCASU)

Entry (reference): `python3 -m mpcasu_qt.app` → `MainWindow`.
Windows artifact: **`MPCASU.exe`** (Qt 6 C++).
Critical path tool. Single-player architecture must be preserved.

Reference map (read before porting):
- `mpcasu_qt/main_window.py` (MainWindow, ~217 KB — the UI/controller surface)
- `mpcasu_qt/videoframe.py` (VideoSurface + NativeHandleAdapter)
- `mpcasu_qt/theme.py`, `casu/design.py` (shared style tokens)
- `mpcasu_qt/webplayers.py` (web-provider tabs; `play_video` = OBSOLETE)
- `mpcasu_qt/app.py` (entry, single-instance lock)
- `mpcasu_backend.py` (LibVLCBackend, LegacyCasuBackend)
- `mpcasu_native_backend.py` (NativeCasuBackend, sinks)
- `mpcasu_playback.py` (PlaybackController)
- `mpcasu_qt/youtube_proxy.py` (loopback transport)
- research: player-mechanics, ui-style-bible, youtube-transport,
  api-contracts-errors-shutdown, vlc-and-webamp-reference
- Git history: `git log -- mpcasu_qt/main_window.py mpcasu_backend.py`

Status legend: NOT_STARTED / ANALYSIS / IMPLEMENTING / BUILDING / TESTING /
WINE_TESTING / BLOCKED / VERIFIED.

================================================================
M-PCASU-1 — APP FOUNDATION
================================================================

## WP-MPCASU-001 Qt application skeleton
- PURPOSE: runnable empty `MPCASU.exe` window under Wine.
- REFERENCES: mpcasu_qt/app.py, mpcasu_qt/main_window.py (window title,
  geometry), ui-style-bible.md.
- INPUTS: none. OUTPUTS: `apps/mpcasu/main.cpp`, `MainWindow.hpp/.cpp` (stub).
- IMPLEMENTATION: QApplication, MainWindow(QMainWindow) with correct title,
  minimum/initial size (metrics: sidebar 240 + workspace + playlist 310),
  red/black background from shared design constants.
- UNIT: window title + geometry under Wine (screenshot gate).
- WINE: `xvfb-run wine MPCASU.exe` → window appears, no missing DLLs.
- COMPATIBILITY: title/geometry == Linux reference.
- ACCEPTANCE: exe starts under Wine, window visible, clean exit.
- DEPENDS: WP-BUILD-001/002/003, WP-DEP-001/002. STATUS: NOT_STARTED.

## WP-MPCASU-002 Single-instance + session restore
- PURPOSE: QLockFile single-instance; restore playlist/geometry/resume.
- REFERENCE: mpcasu_qt/app.py (QLockFile/QLocalServer), main_window session.
- WINE: second launch shows first window. STATUS: NOT_STARTED.

================================================================
M-PCASU-2 — UI STYLE + LAYOUT
================================================================

## WP-MPCASU-010 Sidebar (nav groups + rail mode)
- REFERENCE: main_window (sidebar, NAV_ICONS, rail at <1200 → 70px icons).
- OUTPUTS: Sidebar widget from shared design constants.
- WINE: narrow-width screenshot == rail icons. STATUS: NOT_STARTED.

## WP-MPCASU-011 Top bar + NOW PLAYING
- REFERENCE: main_window topbar; **NOW PLAYING is a fixed heading**; dynamic
  title in separate label; search + ☷ toggle.
- COMPATIBILITY: heading never replaced by title (REQ-UI-004). STATUS: NOT_STARTED.

## WP-MPCASU-012 VideoSurface (native, HWND)
- REFERENCE: videoframe.py (WA_NativeWindow, winId), main_window overlay rule.
- OUTPUTS: `VideoSurface : QWidget`, `Qt::WA_NativeWindow`,
  `reinterpret_cast<HWND>(winId())`, opaque/no-background, overlays hidden in
  video mode.
- WINE: resize/minimize/restore/fullscreen; audio↔video switch; no flicker.
- RISK: HWND lifetime (R3). STATUS: NOT_STARTED.

## WP-MPCASU-013 Transport bar + seek + status + diagnostics + cards
- REFERENCE: main_window transport (shuffle/prev/play/next/repeat/AB/snapshot/
  speed/mute/volume/viz/PiP/fullscreen/tracks/chapters), status bar,
  diagnostics bar, cards.
- WINE: controls operate playback; layout == reference screenshots.
- STATUS: NOT_STARTED.

================================================================
M-PCASU-3 — PLAYBACK CORE (shared casu_playback)
================================================================

## WP-MPCASU-020 PlaybackController (C++)
- REFERENCE: mpcasu_playback.py. OUTPUTS: `CppPlaybackController` with exact
  states EMPTY/LOADING/READY/PLAYING/PAUSED/STOPPED/ENDED/ERROR + transitions.
- UNIT: every transition table test. STATUS: NOT_STARTED.

## WP-MPCASU-021 Backend interface + LibVLCBackend
- REFERENCE: mpcasu_backend.py. RAII libVLC instance/media/player; HWND bind;
  play/pause/seek/duration/position/rate/volume/mute/tracks/chapters/snapshot;
  events; state map 6=ENDED,7=ERROR; zero-time-EOF→ERROR; last_error.
- WINE: local MP4/MKV/MP3 play+seek+volume. RISK: plugin discovery (R2).
- STATUS: NOT_STARTED.

## WP-MPCASU-022 NativeCasuBackend
- REFERENCE: mpcasu_native_backend.py. CASUNAT2 decode, clock/seek/pause,
  WASAPI/Qt audio sink (no PulseAudio), video sink.
- WINE: CASUNAT2 play. STATUS: NOT_STARTED.

## WP-MPCASU-023 Local media pipeline (open→controller→surface)
- REFERENCE: main_window play_selected + _open_external_source.
- WINE: local video/audio on normal surface. STATUS: NOT_STARTED.

================================================================
M-PCASU-4 — LIBRARY / PLAYLIST / SETTINGS / EPG / RECORDING / VIZ
================================================================

## WP-MPCASU-030 Playlist model (shuffle/repeat/next/prev, M3U/PLS)
- REFERENCE: casu/playlist.py, main_window queue. WINE: playlist ops.
- STATUS: NOT_STARTED.

## WP-MPCASU-031 Library (SQLite) + media info dialog
- REFERENCE: casu/library.py. Port schema as-is; Unicode paths.
- STATUS: NOT_STARTED.

## WP-MPCASU-032 Settings (portable JSON/QSettings)
- REFERENCE: casu/settings.py. No registry; settings.json beside app.
- STATUS: NOT_STARTED.

## WP-MPCASU-033 EPG/IPTV (XMLTV + extended M3U)
- REFERENCE: casu/epg.py, playlist.py. STATUS: NOT_STARTED.

## WP-MPCASU-034 Visualizer (audio analysis) + DPI behavior
- REFERENCE: main_window visualizer; shared metrics. DPI 100–200%.
- STATUS: NOT_STARTED.

## WP-MPCASU-035 Recording (QProcess/ffmpeg)
- REFERENCE: casu/recording.py. STATUS: NOT_STARTED.

================================================================
M-PCASU-5 — YOUTUBE (shared transport)
================================================================

## WP-MPCASU-040 yt-dlp wrapper (QProcess, JSON)
- REFERENCE: casu/locations.py, search.py. Tools/yt-dlp.exe.
- WINE: resolve real URL. STATUS: NOT_STARTED.

## WP-MPCASU-041 Loopback transport (QTcpServer/QNAM: Range/206/refresh)
- REFERENCE: mpcasu_qt/youtube_proxy.py; research/youtube-transport.md.
- WINE + real CDN test (REQ-YT-001). STATUS: NOT_STARTED.

## WP-MPCASU-042 YouTube into normal pipeline
- ORDER: stop old → start proxy → open_source → attach → play. No second
  player. WINE + real YouTube. STATUS: NOT_STARTED.

================================================================
M-PCASU-6 — WEB PROVIDERS / INPUT / SHUTDOWN
================================================================

## WP-MPCASU-050 Spotify + web providers (via yt-dlp/HTTP)
- REFERENCE: casu/spotify.py, webproviders.py. Provider tabs optional
  (QtWebEngine or external browser) — documented, not silently dropped.
- STATUS: NOT_STARTED.

## WP-MPCASU-051 Input map (shortcuts/mouse/drag-drop/fullscreen)
- REFERENCE: main_window key/mouse handlers, input-map.
- STATUS: NOT_STARTED.

## WP-MPCASU-052 Shutdown sequence + error model + logging
- REFERENCE: api-contracts-errors-shutdown.md. No lingering processes.
- WINE: clean exit. STATUS: NOT_STARTED.

## WP-MPCASU-060 Packaging integration (into Windows zip) + Wine validation
- REFERENCE: packaging plan. STATUS: NOT_STARTED.

## WINE TEST MATRIX (mpcasu): start, window, resize, minimize/restore, MP3/WAV/
FLAC/MP4/MKV/WebM/CASU/MP5, network stream, YouTube, play/pause/resume/seek/
volume/mute/rate/fullscreen/snapshot, subtitles, audio/video tracks, chapters,
playlist, library, EPG, recording, stop, close, multiple open, media switch,
Unicode/space paths, clean prefix.
