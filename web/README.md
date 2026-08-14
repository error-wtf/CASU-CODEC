# MPCASU Web Player

Start the loopback launcher so the web app can load assets and use its bounded
FFmpeg compatibility fallback:

```bash
cd /path/to/Lino-Codec
python mpcasu_web.py --port 8080
```

Open `http://localhost:8080/web/`. The player supports local audio/video,
multiple files, drag-and-drop, direct media streams, YouTube
embedding, playlist controls, verified JSON sidecars (when their source is
selected at the same time), and standalone CASUNAT1 payload extraction with
browser SHA-256 verification. CASUNAT2 files are integrity-checked and their
selectable video/audio streams are decoded from key states, tile updates and
s16le PCM using browser deflate, Canvas and Web Audio. Selectable native UTF-8
and lossless RGBA bitmap subtitles render against the media clock, and chapter
entries seek directly to their stored PTS. ASS/SSA keeps its playable text
fallback in the browser; libass-styled rendering and output-device selection
remain desktop-only. If the browser rejects a legacy local file, the loopback
launcher transcodes it to VP9/Opus WebM or H.264/AAC MP4 according to the
browser's advertised support. Local CASUNAT1/2 is detected by its magic bytes,
not its filename; if native CASUNAT2 browser playback cannot start, the launcher
verifies and exports it automatically to that same MP4/WebM compatibility path.
It can expose a user-entered HTTP(S), FTP,
RTSP/RTMP, RTP/UDP or SRT source as a cancellable fragmented browser stream.
Local fallback outputs support HTTP byte ranges for seeking; uploads, temporary
outputs and URL sessions are bounded and are deleted when the launcher exits.
Static hosting without `mpcasu-web` retains native browser/CASU support but has
no FFmpeg fallback. Native decoding
fails closed above a cumulative 512 MiB decoded-media budget; use the desktop
player for long or high-resolution CASUNAT2 programs.
