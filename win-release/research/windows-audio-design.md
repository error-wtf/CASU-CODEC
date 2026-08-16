# Windows Audio Design + External Research Log

## Audio: how the reference plays sound

- **Legacy/network media**: libVLC owns audio output. On Windows this uses
  VLC's Windows audio modules (WASAPI/DSound) automatically — no code needed.
- **Native CASU (CASUNAT2)**: decoded in-process by `NativeCasuBackend`
  (`mpcasu_native_backend.py`), which today uses `PulseAudioSink` on Linux.
  This is the only Linux-specific audio piece.

## Windows decision for native CASU audio

Replace PulseAudio with a Windows-native sink:
- **Preferred: WASAPI** (exclusive/event-driven) via a thin C++ wrapper, or
  **Qt Multimedia (`QAudioSink`)** for a simpler, cross-platform abstraction.
- Volume/mute/rate/device-change honored; 44.1/48 kHz, stereo tested.
- libVLC path needs no change (VLC handles its own Windows output).

## External research to perform (deep research log, fill as needed)

| Question | Source priority | Finding | Decision |
|----------|-----------------|---------|----------|
| Qt6 MinGW deployment DLL set | official Qt docs | TBD | controlled CPack |
| qwindows.dll location | official Qt docs | TBD | bundle plugin |
| libVLC Windows plugin discovery | libVLC/vlc docs + vlc tree | TBD | bundle vlc/plugins + env |
| HWND ownership/lifetime | Qt docs | TBD | WA_NativeWindow + keep valid |
| WASAPI vs QtMultimedia sink | MS docs / Qt | TBD | choose WASAPI or QAudioSink |
| FFmpeg Windows redistribution license | FFmpeg docs | TBD | helper exe + license |
| yt-dlp.exe acquisition | yt-dlp releases | TBD | bundle |
| Wine Qt behavior | wine HQ + issues | TBD | test |
| QtWebEngine optional bundling | Qt docs | TBD | provider tabs decision |

This log will be filled with concrete findings during implementation; each
entry keeps QUESTION/SOURCES/FINDING/RELEVANCE/DECISION.
