# Shared Libraries — Roadmaps (casu_codec, casu_media, casu_network,
casu_playback, casu_webapi)

## casu_codec
Reference: casu/core.py (analyze), casu/native_v2 (video), casu/mp5,
casu/transcode.py (ffmpeg arg builder), casu/scheduler.py, casu/export.py.
- WP-CODEC-001 analyze (state analysis modes, ANALYSIS_MODES) — semantic equal.
- WP-CODEC-002 ffmpeg wrapper (QProcess arg arrays; no shell strings).
- WP-CODEC-003 ffprobe wrapper (format/streams/duration/tags).
- WP-CODEC-004 media presets + quality options (remux/balanced/high/small/
  lossless) + output extensions.
- WP-CODEC-005 export (CASU→media).
- STATUS all: NOT_STARTED. Gates: golden + Wine.

## casu_media
Reference: casu/probe.py, casu/thumbnail.py, casu/waveform.py, casu/tags.py,
casu/filetypes.py.
- WP-MEDIA-001 probe (ffprobe) → MediaInfo.
- WP-MEDIA-002 thumbnail extraction.
- WP-MEDIA-003 waveform (7 helpers) for visualizer.
- WP-MEDIA-004 tags (ID3v2/APIC/cover).
- WP-MEDIA-005 kind detection (detect_casu_kind).
- STATUS all: NOT_STARTED.

## casu_network
Reference: casu/locations.py, casu/search.py, casu/spotify.py,
casu/webproviders.py, urllib usage.
- WP-NET-001 URL/HTTP client (QNetworkAccessManager), schemes, timeouts.
- WP-NET-002 yt-dlp wrapper (resolve/search/title) — QProcess, JSON, timeout.
- WP-NET-003 spotify metadata/matching (yt-dlp/spotDL) — same contract.
- WP-NET-004 webproviders URL builders.
- WP-NET-005 HTTP Range/206 primitives shared with youtube transport + web
  backend media serve.
- STATUS all: NOT_STARTED.

## casu_playback
Reference: mpcasu_playback.py, mpcasu_backend.py, mpcasu_native_backend.py,
media_backend.py.
- WP-PLAY-001 CppPlaybackController (states/transitions + unit table).
- WP-PLAY-002 PlaybackBackend interface (abstract).
- WP-PLAY-003 LibVLCBackend C++ (RAII, HWND, events, state map, last_error).
- WP-PLAY-004 NativeCasuBackend (decode, clock/seek/pause, WASAPI/Qt sink).
- WP-PLAY-005 VideoSink/AudioSink interfaces.
- STATUS all: NOT_STARTED.

## casu_webapi
Reference: web_casu.py, TranscodeStore.
- WP-WEBAPI-001 HTTP server (loopback, host validation) + JSON body + size caps.
- WP-WEBAPI-002 Endpoint handlers (resolve/search/title/spotify/catalog/
  stream-proxy/transcode/media/version).
- WP-WEBAPI-003 TranscodeStore (token registry, upload, live-transcode,
  temp cleanup).
- WP-WEBAPI-004 Range/HEAD media serving (shared primitives).
- WP-WEBAPI-005 Security (allow-list, path traversal, malformed range).
- STATUS all: NOT_STARTED.

All libraries are built once and linked by every tool (no per-tool copies);
unit + golden + Wine gates per WP.
