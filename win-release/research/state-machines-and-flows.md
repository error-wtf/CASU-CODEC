# State Machines + Data Flow + Timing/Threading/Ownership

Grounded in the frozen reference (class inventory extracted via AST).

## Playback state machine (`mpcasu_playback.py` → PlaybackController)

```
        EMPTY ──attach(backend)──▶ LOADING ──▶ READY
                                     │ (exception) └──▶ ERROR
READY ──play()──▶ PLAYING ──pause()──▶ PAUSED ──resume()──▶ PLAYING
PLAYING/PAUSED ──stop()──▶ STOPPED
READY ──close()──▶ EMPTY
(backend event/media state: 6→ENDED, 7→ERROR; zero-time-EOF+no tracks → ERROR)
```
Windows: `CppPlaybackController`; same transitions, unit-tested per edge.

## Main window / source flow

```
select → stop(old, stop_youtube=flag) → detect stage (audio/video) →
  backend = LibVLCBackend(handle) [or NativeCasuBackend] →
  open_source / open_casu → controller.attach → controller.play →
  surface active, overlays hidden for video
YouTube: stop old → proxy.start(resolved, refresh) → open_source(loopback) → attach → play
```

## Data flows

- **Local file**: File → `_source_for`/resolve → backend → decode → VideoSurface.
- **CASU**: container → validate → manifest → NativeCasuBackend (or source
  resolve for sidecar; MP5 → attachment extract/verify) → audio/video sink.
- **YouTube**: URL → `resolve_media_location` → transport → LibVLCBackend →
  controller → surface.
- **Web (backend)**: Browser → /api/* → `web_casu.py` (yt-dlp/transcode/
  catalog/proxy) → media → browser.
- **Converter** (`casu/jobs.py` ConversionEngine): probe → profile →
  ffmpeg/casu → progress → result.
- **Recording** (`casu/recording.py` MediaRecorder): active source → FFmpeg
  → file.

## Timing / threading / ownership (Windows must preserve)

- GUI updates only via queued signals; background workers (resolve, transcode,
  thumbnail, scan, viz) return over bridges; **generation counter** drops stale
  async results.
- **YouTube transport lifecycle**: stop old BEFORE start new; new proxy must
  survive until libVLC opens it (premature-stop bug documented).
- **libVLC**: instance/media/player owned by backend (RAII in C++); no
  double-close; event callbacks must not run UI work directly.
- **Web backend / proxy**: QTcpServer sockets bounded, backpressure, clean
  shutdown (no leak of sockets/threads).
- **Processes** (yt-dlp/ffmpeg): QProcess arg-arrays, no shell strings;
  terminate on stop/exit.
- **DB/audio/visualizer workers**: serialized to GUI thread for UI,
  decoder/audio own their own timing.
