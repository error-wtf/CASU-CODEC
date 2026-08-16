"""Tests for the loopback YouTube transport proxy.

The proxy is transport only: it receives an already-resolved media URL (from
the shared web-casu resolver) and serves it to libVLC with correct HTTP Range
handling. No yt-dlp, no HTML player, no full-RAM buffering.
"""
from __future__ import annotations

import http.client
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import mpcasu_qt.youtube_proxy as ytproxy


DATA = bytes(range(256)) * 1024  # 256 KiB of deterministic bytes


def _make_upstream(*, always_403: bool = False, extra_headers=None):
    """Fresh upstream stub per test (no shared class state between tests)."""
    state = {"requests": 0, "seen": []}
    extras = dict(extra_headers or {})

    class Upstream(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_HEAD(self):
            self._respond(head=True)

        def do_GET(self):
            self._respond(head=False)

        def _respond(self, *, head: bool):
            state["requests"] += 1
            state["seen"].append(dict(self.headers))
            if always_403:
                self.send_error(403)
                return
            range_value = self.headers.get("Range")
            if range_value:
                spec = range_value.removeprefix("bytes=")
                if spec.startswith("-"):
                    length = min(int(spec[1:]), len(DATA))
                    body = DATA[-length:]
                    start = len(DATA) - length
                    end = len(DATA) - 1
                else:
                    start_s, _, end_s = spec.partition("-")
                    start = int(start_s)
                    end = int(end_s) if end_s else len(DATA) - 1
                    end = min(end, len(DATA) - 1)
                    body = DATA[start:end + 1]
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(DATA)}")
            else:
                body = DATA
                self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Accept-Ranges", "bytes")
            for name, value in extras.items():
                self.send_header(name, value)
            self.end_headers()
            if not head:
                self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/videoplayback"
    return server, thread, url, state


def _stop(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def _get(url: str, *, range_header: str | None = None, head: bool = False):
    headers = {"Range": range_header} if range_header else {}
    request = urllib.request.Request(url, headers=headers,
                                     method="HEAD" if head else "GET")
    return urllib.request.urlopen(request, timeout=5)


def test_range_request_is_forwarded_as_partial_content():
    server, thread, url, state = _make_upstream()
    proxy = ytproxy.YouTubeMediaProxy()
    try:
        media = proxy.start(url)  # preflight already proves the upstream
        with _get(media, range_header="bytes=100-199") as response:
            assert response.status == 206
            assert response.headers["Content-Range"] == f"bytes 100-199/{len(DATA)}"
            assert response.headers["Accept-Ranges"] == "bytes"
            assert response.headers["Content-Length"] == "100"
            assert response.read() == DATA[100:200]
    finally:
        proxy.stop()
        _stop(server, thread)


def test_full_get_streams_every_byte_without_ram_buffer():
    server, thread, url, _state = _make_upstream()
    proxy = ytproxy.YouTubeMediaProxy()
    try:
        media = proxy.start(url)
        with _get(media) as response:
            assert response.status == 200
            assert int(response.headers["Content-Length"]) == len(DATA)
            assert response.read() == DATA
        # streaming transport: no whole-video buffer anywhere on the proxy
        assert not hasattr(proxy, "_buffer")
    finally:
        proxy.stop()
        _stop(server, thread)


def test_seek_requests_at_different_offsets():
    server, thread, url, _state = _make_upstream()
    proxy = ytproxy.YouTubeMediaProxy()
    try:
        media = proxy.start(url)
        for start, end in ((0, 1023), (200_000, 262_143), (1024, 1024)):
            with _get(media, range_header=f"bytes={start}-{end}") as response:
                assert response.status == 206
                assert response.read() == DATA[start:end + 1]
    finally:
        proxy.stop()
        _stop(server, thread)


def test_open_ended_range_from_offset():
    """bytes=N- is forwarded and answered with 206 + real remaining length."""
    server, thread, url, _state = _make_upstream()
    proxy = ytproxy.YouTubeMediaProxy()
    try:
        media = proxy.start(url)
        with _get(media, range_header="bytes=123456-") as response:
            assert response.status == 206
            assert response.headers["Content-Range"] == (
                f"bytes 123456-{len(DATA) - 1}/{len(DATA)}")
            assert response.read() == DATA[123456:]
    finally:
        proxy.stop()
        _stop(server, thread)


def test_open_ended_range_from_zero():
    server, thread, url, _state = _make_upstream()
    proxy = ytproxy.YouTubeMediaProxy()
    try:
        media = proxy.start(url)
        with _get(media, range_header="bytes=0-") as response:
            assert response.status == 206
            assert response.headers["Content-Range"] == (
                f"bytes 0-{len(DATA) - 1}/{len(DATA)}")
            assert response.read() == DATA
    finally:
        proxy.stop()
        _stop(server, thread)


def test_suffix_range():
    """bytes=-K requests the last K bytes and must stay a 206."""
    server, thread, url, _state = _make_upstream()
    proxy = ytproxy.YouTubeMediaProxy()
    try:
        media = proxy.start(url)
        with _get(media, range_header="bytes=-65536") as response:
            assert response.status == 206
            assert response.headers["Content-Range"] == (
                f"bytes {len(DATA) - 65536}-{len(DATA) - 1}/{len(DATA)}")
            assert response.read() == DATA[-65536:]
    finally:
        proxy.stop()
        _stop(server, thread)


def test_hop_by_hop_headers_never_forwarded():
    """Hop-by-hop headers from upstream must not leak; only media metadata is kept."""
    server, thread, url, _state = _make_upstream(extra_headers={
        "Connection": "close",
        "Keep-Alive": "timeout=5",
        "Proxy-Connection": "keep-alive",
        "X-Upstream-Marker": "must-not-leak",
    })
    proxy = ytproxy.YouTubeMediaProxy()
    try:
        media = proxy.start(url)
        with _get(media, range_header="bytes=0-15") as response:
            headers = {k.lower(): v for k, v in response.headers.items()}
            assert headers.get("content-type") == "video/mp4"
            assert headers.get("accept-ranges") == "bytes"
            assert "content-range" in headers
            assert "connection" not in headers
            assert "keep-alive" not in headers
            assert "proxy-connection" not in headers
            assert "x-upstream-marker" not in headers
    finally:
        proxy.stop()
        _stop(server, thread)


def test_upstream_headers_mirror_webcasu_browser_profile():
    """Browser UA, no Referer, no cookies — exactly what web-casu sends."""
    server, thread, url, state = _make_upstream()
    proxy = ytproxy.YouTubeMediaProxy()
    try:
        media = proxy.start(url)
        with _get(media, range_header="bytes=0-15") as response:
            assert response.status == 206
        seen = {k.lower(): v for k, v in state["seen"][-1].items()}
        assert seen["user-agent"].startswith("Mozilla/5.0")
        assert "referer" not in seen
        assert "cookie" not in seen
        assert seen["range"] == "bytes=0-15"
    finally:
        proxy.stop()
        _stop(server, thread)


def test_403_triggers_single_transparent_refresh():
    stale_server, stale_thread, stale_url, stale_state = _make_upstream(always_403=True)
    fresh_server, fresh_thread, fresh_url, _fresh_state = _make_upstream()
    refreshes = []
    proxy = ytproxy.YouTubeMediaProxy()
    try:
        media = proxy.start(
            stale_url,
            refresh=lambda: refreshes.append(1) or fresh_url,
        )
        assert refreshes == [1]  # preflight already recovered the URL
        assert stale_state["requests"] == 1  # not hammered
        with _get(media, range_header="bytes=0-31") as response:
            assert response.status == 206
            assert response.read() == DATA[:32]
        assert refreshes == [1]  # steady state: no further re-resolves
    finally:
        proxy.stop()
        _stop(stale_server, stale_thread)
        _stop(fresh_server, fresh_thread)


def test_persistent_403_without_refresh_is_a_clean_error():
    server, thread, url, _state = _make_upstream(always_403=True)
    proxy = ytproxy.YouTubeMediaProxy()
    try:
        with pytest.raises(ytproxy.YouTubeProxyError):
            proxy.start(url)
    finally:
        proxy.stop()
        _stop(server, thread)


def test_head_request_supported():
    server, thread, url, _state = _make_upstream()
    proxy = ytproxy.YouTubeMediaProxy()
    try:
        media = proxy.start(url)
        with _get(media, head=True) as response:
            assert response.status == 200
            assert int(response.headers["Content-Length"]) == len(DATA)
            assert response.read() == b""
    finally:
        proxy.stop()
        _stop(server, thread)


def test_no_player_page_and_unknown_paths_404():
    """There is no HTML/<video> player endpoint anymore — bytes only."""
    server, thread, url, _state = _make_upstream()
    proxy = ytproxy.YouTubeMediaProxy()
    try:
        media = proxy.start(url)
        base = media.rsplit("/", 1)[0]
        for path in (f"{base}/player", f"{base}/", base.rsplit("/", 1)[0] + "/"):
            with pytest.raises(urllib.error.HTTPError) as excinfo:
                urllib.request.urlopen(path, timeout=5)
            assert excinfo.value.code == 404
    finally:
        proxy.stop()
        _stop(server, thread)


def test_untrusted_host_rejected():
    server, thread, url, _state = _make_upstream()
    proxy = ytproxy.YouTubeMediaProxy()
    try:
        media = proxy.start(url)
        port = int(media.split(":")[2].split("/")[0])
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        connection.putrequest("GET", media.split(f":{port}", 1)[1], skip_host=True)
        connection.putheader("Host", "evil.example")
        connection.endheaders()
        response = connection.getresponse()
        response.read()
        assert response.status == 421
        connection.close()
    finally:
        proxy.stop()
        _stop(server, thread)


def test_resolved_url_must_be_http():
    proxy = ytproxy.YouTubeMediaProxy()
    with pytest.raises(ytproxy.YouTubeProxyError):
        proxy.start("not-a-url")
