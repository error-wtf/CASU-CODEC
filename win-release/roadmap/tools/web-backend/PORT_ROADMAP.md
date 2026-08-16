# CASU-Web-Backend — Windows Port Roadmap (Tool: TOOL-WEB-BACKEND)

Entry (reference): `python3 web_casu.py` (MPCASUWebServer + WebPlayerHandler +
TranscodeStore). Windows artifact: **`CASU-Web-Backend.exe`** (Qt 6 C++ native
HTTP server on loopback). Frontend `web/` is reused **verbatim**; the backend
API contract is the compatibility baseline (research/web-api-contract.md).

Reference map:
- `web_casu.py` (do_POST/do_GET/do_HEAD, _resolve/_search/_youtube_title/
  _spotify_metadata/_stream_proxy/_serve_transcoded_file, TranscodeStore,
  _trusted_request, range handling)
- `casu/locations.py`, `casu/search.py`, `casu/spotify.py`,
  `casu/webproviders.py`, `casu/epg.py` (fetch_document), `casu/transcode.py`
- research/web-api-contract.md (endpoint + security table)

Every endpoint gets its own WP. First the contract + security primitives,
then implementation per endpoint. Frontend must not know whether it talks to
Python-Linux or C++-Windows.

Status legend: NOT_STARTED / ANALYSIS / IMPLEMENTING / BUILDING / TESTING /
WINE_TESTING / BLOCKED / VERIFIED.

================================================================
M-WEB-1 — HTTP + SECURITY PRIMITIVES (shared casu_webapi)
================================================================

## WP-WEB-001 HTTP server on loopback (QTcpServer) + host validation
- REFERENCE: web_casu.py `_trusted_request` (loopback only, no 0.0.0.0),
  DNS-rebinding protection via Host header check.
- WINE: binds 127.0.0.1 only; bad Host rejected. STATUS: NOT_STARTED.

## WP-WEB-002 Request size caps + body reader + JSON parsing
- REFERENCE: Content-Length caps (≤64 KiB JSON, ≤32 MiB catalog), malformed
  JSON → 400. STATUS: NOT_STARTED.

## WP-WEB-003 Static frontend serve (web/ index.html, app.js, …)
- REFERENCE: super().do_GET() for non-API paths; bundle `web/` verbatim.
- WINE: browser loads page. STATUS: NOT_STARTED.

## WP-WEB-004 Range + HEAD media serving primitives (shared with transport)
- REFERENCE: `_serve_transcoded_file` (Range bytes=N-, suffix, 206/200,
  Content-Range/Length, HEAD). Reuse with youtube transport primitives.
- WINE: browser seeks transcoded media. STATUS: NOT_STARTED.

================================================================
M-WEB-2 — API ENDPOINTS (one WP each)
================================================================

## WP-WEB-010 GET /api/version
- Returns {version}; frontend reload-on-mismatch.
- WINE/curl: 200 {version}. STATUS: NOT_STARTED.

## WP-WEB-011 POST /api/resolve (yt-dlp resolve; YouTube/Spotify)
- REFERENCE: _resolve + casu/locations. QProcess yt-dlp.exe, JSON parse,
  timeout. STATUS: NOT_STARTED.

## WP-WEB-012 POST /api/search (yt-dlp search)
- REFERENCE: _search + casu/search. STATUS: NOT_STARTED.

## WP-WEB-013 POST /api/youtube-title
- REFERENCE: _youtube_title. STATUS: NOT_STARTED.

## WP-WEB-014 POST /api/spotify-metadata
- REFERENCE: _spotify_metadata + casu/spotify. STATUS: NOT_STARTED.

## WP-WEB-015 POST /api/catalog-url (fetch remote M3U/XMLTV, CORS bypass)
- REFERENCE: fetch_document + _catalog; ≤32 MiB. STATUS: NOT_STARTED.

## WP-WEB-016 GET /api/stream-proxy (allow-list relay)
- REFERENCE: _stream_proxy; allow-list (SSRF), loopback. STATUS: NOT_STARTED.

## WP-WEB-017 POST /api/transcode-file + /api/transcode-url + /api/media/{token}
- REFERENCE: TranscodeStore (register_url/transcode_upload), _serve
  (file vs live-transcode), QProcess ffmpeg, token-scoped. Upload bounded.
- WINE: upload, transcode, stream, seek. STATUS: NOT_STARTED.

================================================================
M-WEB-3 — LIFECYCLE + PACKAGING
================================================================

## WP-WEB-020 Shutdown (stop server, terminate ffmpeg/yt-dlp, temp cleanup)
- REFERENCE: api-contracts-errors-shutdown.md. No lingering processes.
- WINE: clean exit. STATUS: NOT_STARTED.

## WP-WEB-030 Bundle into Windows zip + clean-prefix browser↔backend test
- REFERENCE: packaging plan. STATUS: NOT_STARTED.

## WINE matrix (web backend): start, port, API, upload, stream, range,
YouTube, shutdown. Browser frontend operates identically vs Python backend.

## Security acceptance (REQ-WEB-002): loopback only, host validation,
request caps, path-traversal-safe media tokens, allow-list proxy, malformed
range rejected. No open binding.
