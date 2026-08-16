# Player Mechanics + State Machines (read-only analysis)

Sources: `mpcasu_playback.py`, `mpcasu_backend.py` (LibVLCBackend),
`mpcasu_qt/main_window.py`, `mpcasu_qt/videoframe.py`, `mpcasu_native_backend.py`.

## Architecture (must be preserved 1:1)

```
UI (MainWindow)
   ↓
PlaybackController        ← owns playback state machine
   ↓
Backend interface
   ├── LibVLCBackend      (ctypes → libVLC C API; legacy/network media)
   └── NativeCasuBackend  (native CASUNAT2 decode + sinks)
   ↓
VideoSurface (native window, libVLC draws into it; Qt never paints over)
```

Single player only. YouTube must enter this same pipeline.

## PlaybackController (mpcasu_playback.py)

States: `EMPTY, LOADING, READY, PLAYING, PAUSED, STOPPED, ENDED, ERROR`.

Transitions observed:
- attach(backend, source): close old → LOADING → READY (exception → ERROR).
- play(): requires backend → backend.play() → PLAYING.
- pause_or_resume(): PAUSED→PLAYING / PLAYING→PAUSED.
- stop(): backend.stop() → STOPPED (EMPTY if no backend).
- close(): backend.close() → EMPTY.
- seek/position/duration delegate to backend.

Port target: `CppPlaybackController` with the exact same states and
transitions; tests for every transition.

## Backend interface (what a C++ PlaybackBackend must implement)

open/open_source, play, pause, resume, stop, seek, position, duration, state,
set/get volume, mute, rate, audio/video/subtitle track selection + counts,
chapters, snapshot, media_state_code, capabilities, close, last_error.
RAII ownership of libVLC instance/media/player.

## VideoSurface rules (from videoframe.py + main_window)

- `Qt::WA_NativeWindow`; libVLC renders into `winId()`; Qt keeps
  `WA_OpaquePaintEvent/WA_NoSystemBackground`, `setAutoFillBackground(false)`.
- When video is active: caption/badges/empty-hint overlays hidden, no
  `raise_()` over the surface (flicker). Windows: `HWND = winId()`,
  `libvlc_media_player_set_hwnd`.
- Fullscreen/resize must not repaint over the native video.

## Key flows

**Local file:** play_selected → stop old → detect stage (audio/video) →
backend = LibVLCBackend(handle) → open → controller.attach → play.

**Network stream:** resolve_media_location (shared web-casu resolver) →
LibVLCBackend.open_source(loopback or direct) → controller.

**YouTube:** URL → resolve_media_location → YouTubeMediaProxy (loopback
byte/range transport) → media URL → LibVLCBackend.open_source →
PlaybackController → VideoSurface. Lifecycle rule (fixed bug): the previous
session/proxy is stopped BEFORE the new proxy is started; the new proxy is
never destroyed by playback cleanup before libVLC opens it.

**Native CASU:** NativeCasuBackend decodes in-process; own clock/seek/pause.

## Timing / lifecycle traps found (port must avoid re-introducing)

1. Proxy killed by stop() before libVLC opened it → “Playback error detected”.
   Order: stop old → start proxy → open.
2. AudioContext (web) suspended → media muted. Desktop analog: don’t attach
   the native video/audio surface while the backend isn’t running.
3. `Number(null)=0` style defaults → never mute at start (volume default 1).
4. State() maps libVLC media/player 6=Ended, 7=Error; zero-time EOF with no
   tracks → ERROR (VLC 3 quirk). Keep this mapping in C++.
5. Background resolve → generation counter so stale results are dropped;
   GUI updates only via queued signals.
