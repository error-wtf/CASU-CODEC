# API Contracts + Error Model + Shutdown

## Backend interface (from mpcasu_backend.py + mpcasu_native_backend.py)

`PlaybackBackend` (C++ abstract): open_source/open_casu, play, pause, resume,
stop, seek(sec), position(), duration(), state(), set/get volume, mute, rate,
audio/video/subtitle track count + select + descriptions, chapters, snapshot,
media_state_code, capabilities, last_error, close. Ownership: backend owns
libVLC resources (RAII); surface handle set at construction; no shared
ownership of surface with UI overlays.

`VideoSink`/`AudioSink` (media_backend.py, native backend): native CASU draws
frames/PCM into sinks; PulseAudio is Linux-only → WASAPI/Qt on Windows.

## Settings & Library schema

- `SettingsStore` (casu/settings.py) → portable JSON/QSettings (no registry).
- `MediaLibrary` (casu/library.py): LibraryItem, PlaybackPreferences,
  MediaBookmark; SQLite. Port schema as-is; migrations supported.

## Error model (typed exceptions → user messages)

CasuError/NativeCasuError/Mp5Error/EpgError/PlaylistError/RecordingError/
SearchError/SpotifyError/ProbeError/TranscodeError/ExportError/BackendError/
WebPlayerError/CasuCancelled/ConversionCancelled/LocationResolutionError.
Windows: typed C++ exceptions → user-facing toast/status; never swallowed;
libVLC/ffmpeg/yt-dlp/network errors made diagnosable (logs).

## Shutdown sequence (order matters)

1. stop UI timers/viz.
2. terminate subprocesses (yt-dlp/ffmpeg/recorder).
3. stop YouTube transport / web server sockets.
4. stop+close backend (libVLC instance release).
5. persist settings/library/session.
6. join worker threads.
7. release DB.

Windows must test: no lingering processes/handles after exit (REQ-PLAYER-006).

## Ambiguities / decisions

- `web/README.md` → `mpcasu_web.py` missing (stale doc). Decision: OBSOLETE.
- `WebPlayerTabs.play_video` HTML `<video>` for YouTube: OBSOLETE, not ported.
- QtWebEngine provider tabs: optional (bundle or external browser), documented.
- Native CASU audio sink: WASAPI/Qt (see windows-audio-design.md).
