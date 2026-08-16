# Web API Contract (web-casu backend → Windows port)

Source: `web_casu.py` (reference Python backend). Frontend `web/` talks to
these endpoints. The Windows backend must implement the **same contract** so
the browser frontend can be reused unchanged.

## Endpoints

| Method | Path | Input | Output | Notes |
|--------|------|-------|--------|-------|
| GET | /api/version | – | {version} | version check; frontend reloads on mismatch |
| POST | /api/transcode-file | binary body + `X-MPCASU-Filename`, `X-MPCASU-Target` (mp4/webm) | {url:/api/media/{token}, kind} | upload → transcode → serve |
| POST | /api/transcode-url | {url, target} ≤64 KiB | {url, kind} | fetch remote → transcode |
| POST | /api/catalog-url | {url} ≤64 KiB | catalog bytes (XML/m3u) | fetch EPG/playlist server-side (CORS bypass) |
| POST | /api/search | {query, …} | search results | yt-dlp YouTube search |
| POST | /api/resolve | {url, title, artist} | {url} | yt-dlp resolve (YouTube/Spotify) |
| POST | /api/youtube-title | {url} | {title, uploader} | yt-dlp title fetch |
| POST | /api/spotify-metadata | {url} | metadata | spotDL/yt-dlp matching |
| GET | /api/stream-proxy | ?url= | streamed bytes | cross-origin stream relay (allow-list) |
| GET/HEAD | /api/media/{token} | – | transcoded media | token-scoped, range-capable |
| GET | static | / | web/ frontend | serves index.html, app.js, … |

## Security requirements (must port, from web_casu.py + php/)

- **Loopback only** (127.0.0.1/::1); no external binding.
- **Host validation** (trusted loopback host) — DNS-rebinding protection.
- Request size caps (≤64 KiB for JSON, ≤32 MiB catalog, upload bounded).
- `stream-proxy` uses an **allow-list** (SSRF protection).
- Media tokens are random; path traversal blocked; malformed ranges rejected.
- CORS `Access-Control-Allow-Origin: *` for browser access (loopback service).

## Windows port

`casu_web_backend` (C++/Qt: QTcpServer + HTTP parsing, or small embedded
HTTP). Reuse `web/` frontend verbatim. Endpoint contract + security tests
first, implementation second. Range/206 handling identical to the YouTube
loopback transport (shared HTTP primitives).
