# UNDERSTANDING CHECK (self-verified against reference code)

| # | Question | Answer (grounded) |
|---|----------|-------------------|
| 1 | How does MPCASU start? | `mpcasu_qt/app.py` → QApplication → MainWindow; session restore (playlist/geometry/resume); sidebar nav; player page default. |
| 2 | Local MP4 playback? | play_selected → stop old → stage detect → `LibVLCBackend(surface.handle)` → open → `controller.attach` → `controller.play`; libVLC draws into VideoSurface. |
| 3 | CASU playback? | CASUNAT1/legacy resolved to source + verified; CASUNAT2 → `NativeCasuBackend` (in-process decode + sinks); MP5 → attachment extraction/verify or libVLC. |
| 4 | YouTube? | URL → `resolve_media_location` (shared web-casu resolver) → loopback byte/range proxy → media URL → `LibVLCBackend.open_source` → PlaybackController → same VideoSurface. |
| 5 | Web player? | Python backend (`web_casu.py`) serves `web/` frontend; /api/* for search/resolve/title/transcode/catalog/stream-proxy/media. |
| 6 | Pure Web vs backend web? | Pure: static, no server (IFrame API, oEmbed, hls.js, client CASU). Backend: same browser UI but Python server does yt-dlp/transcode/proxy. |
| 7 | Converter? | `casu_converter.py` (Tk GUI): batch conversion, CASU import/export, formats via ffmpeg + casu core. |
| 8 | Recording? | `casu/recording.py` via FFmpeg helper (QProcess-equivalent subprocess). |
| 9 | Playlist? | `casu/playlist.py` + queue model in MainWindow; shuffle/repeat/next/prev; M3U/PLS import/export. |
| 10 | Library? | `casu/library.py` SQLite (paths, progress, playback prefs, watched folders). |
| 11 | EPG? | `casu/epg.py` XMLTV parse; `casu/playlist.py` extended-M3U tvg attrs; NOW/NEXT guide. |
| 12 | VideoSurface owner? | The window (`VideoSurface` widget); libVLC draws into its native id; Qt never paints over during video. |
| 13 | Playback state owner? | `PlaybackController` (EMPTY…ERROR); UI observes, never owns. |
| 14 | libVLC does? | access/demux/decode/av output, tracks, chapters, snapshot, rate, events, error states (media 6/7). |
| 15 | MPCASU itself does? | UI, controller state machine, source resolution, YouTube transport, playlists/library/EPG/settings, stage detection, overlay policy. |
| 16 | FFmpeg does? | probe (ffprobe), transcode/thumbnail/waveform/recording helpers. |
| 17 | yt-dlp does? | YouTube/Spotify resolve + search + titles; never a player. |
| 18 | Qt does? | GUI framework, widgets, layout, timers, threads; QtWebEngine only for web-player tabs (Spotify/Tidal), NOT for YouTube video. |
| 19 | Webamp role? | style/interaction reference (playlist, controls, skin); embedded next to pure-web on the WP page. |
| 20 | VLC role? | playback mechanics reference; MPCASU uses libVLC C API and must not duplicate its work. |
| 21 | Linux-specific to replace? | PulseAudio, X11 set_xwindow, VLC_PLUGIN_PATH, POSIX paths, subprocess discovery, /tmp. |
| 22 | Identical on Windows? | UI look/behavior, playback feel, NOW PLAYING, playlist/library/EPG/settings behavior, CASU format output. |
| 23 | Functionally identical? | codec semantics, integrity checks, API contracts, exit codes. |
| 24 | May differ technically? | internals (C++ vs Python), audio sink (WASAPI vs Pulse), window embedding (HWND vs X11), HTTP stack. |
| 25 | Release-critical? | build, Qt deploy, libVLC embed+plugins, VideoSurface/HWND, PlaybackController, codec core, packaging, Wine gates, YouTube real run. |

**Verdict: understanding sufficient to build the roadmap.**
