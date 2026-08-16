# YouTube Transport (Windows port spec)

Reference: `mpcasu_qt/youtube_proxy.py` (frozen). This is the **transport** in
`URL → resolver → transport → LibVLCBackend → PlaybackController → VideoSurface`.

## Contract (must be preserved in C++)

- `YouTubeMediaProxy.start(media_url, refresh=callable) -> loopback URL`
  - media_url is **already resolved** by the shared web-casu resolver
    (`casu.locations.resolve_media_location`); the proxy never touches yt-dlp.
  - `refresh` re-runs the shared resolver once per request on 403/410.
  - preflight (`GET bytes=0-0`) before returning, so a dead URL is surfaced
    as a clean error instead of a libVLC hang.
- `stop(reason=...)` — loopback only, token path, no external binding.
- HTTP: GET + HEAD, Range forwarded, 206 + Content-Range + Content-Length +
  Accept-Ranges relayed; open-ended and suffix ranges; hop-by-hop headers
  (Connection/Keep-Alive/Transfer-Encoding) never forwarded; streamed in
  256 KiB chunks, never buffered in RAM.
- Request profile mirrors web-casu browser: browser User-Agent, no Referer
  (Referrer-Policy: no-referrer), no cookies.
- **No HTML, no `<video>`, no iframe, no playback state, no second player.**

## Lifecycle rule (the “Playback error detected” bug fix)

Order must be: **stop old session → start the new proxy → open_source → play.**
The new proxy is never destroyed by playback cleanup before libVLC opens it
(`stop(stop_youtube=False)` + `preserve_proxy=True` semantics).

## Windows port

- `YTTransport` (C++/Qt): QTcpServer (loopback, random port, random token) +
  QNetworkAccessManager upstream; Range parsing (bytes=N-, bytes=-K),
  206 handling, chunked streaming with backpressure, 403/410 → one refresh.
- Same HTTP primitives reused by the web-backend media server (Range/206).
- Real CDN test required (not just fake upstream).
