"""Headless boundary test: embedded libVLC consumes the loopback transport.

This is exactly the boundary the GUI "Playback error detected" symptom points
at:

    LibVLCBackend.open_source(proxy_media_url)

No GUI, no network, no yt-dlp: a generated audio file is served over loopback
through the real YouTubeMediaProxy. If embedded libVLC opens, decodes and
seeks that URL, then the transport boundary is proven — and any remaining GUI
failure must be a lifecycle/integration problem, not an HTTP-compat problem.
"""
from __future__ import annotations

import ctypes.util
import http.server
import shutil
import subprocess
import threading
import time

import pytest

from mpcasu_backend import LibVLCBackend, PlaybackState
from mpcasu_qt.youtube_proxy import YouTubeMediaProxy

pytestmark = pytest.mark.media


class _HeadlessSurface:
    def winfo_id(self):
        return 0


def _make_tone(tmp_path):
    fixture = tmp_path / "tone.wav"
    generated = subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "sine=frequency=733:sample_rate=48000",
        "-t", "2.0", "-c:a", "pcm_s16le", str(fixture),
    ], capture_output=True, text=True, check=False)
    if generated.returncode != 0:
        pytest.skip(f"FFmpeg PCM encoder unavailable: {generated.stderr.strip()}")
    return fixture


def _range_media_server(fixture):
    data = fixture.read_bytes()

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_HEAD(self):
            self._respond(head=True)

        def do_GET(self):
            self._respond(head=False)

        def _respond(self, *, head: bool):
            range_value = self.headers.get("Range")
            if range_value:
                spec = range_value.removeprefix("bytes=")
                if spec.startswith("-"):
                    length = min(int(spec[1:]), len(data))
                    body = data[-length:]
                    start = len(data) - length
                    end = len(data) - 1
                else:
                    start_s, _, end_s = spec.partition("-")
                    start = int(start_s)
                    end = int(end_s) if end_s else len(data) - 1
                    end = min(end, len(data) - 1)
                    body = data[start:end + 1]
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
            else:
                body = data
                self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            if not head:
                self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_address[1]}/tone.wav"


def _stop_server(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=2.0)


@pytest.mark.media
@pytest.mark.skipif(
    not ctypes.util.find_library("vlc") or not shutil.which("ffmpeg"),
    reason="libVLC/FFmpeg unavailable")
def test_libvlc_opens_decodes_and_seeks_loopback_proxy_media(tmp_path):
    fixture = _make_tone(tmp_path)
    server, thread, upstream = _range_media_server(fixture)
    proxy = YouTubeMediaProxy()
    backend = LibVLCBackend(
        _HeadlessSurface(), runtime_options=("--aout=dummy", "--vout=dummy"))
    try:
        media = proxy.start(upstream)
        backend.open_source(media)
        backend.play()
        deadline = time.monotonic() + 5.0
        position = 0.0
        tracks = 0
        state = backend.state()
        while time.monotonic() < deadline:
            position = max(position, backend.position())
            tracks = max(tracks, backend.audio_track_count())
            state = backend.state()
            if position >= 0.05 and tracks > 0:
                break
            if state is PlaybackState.ERROR:
                break
            time.sleep(0.02)
        assert state is not PlaybackState.ERROR, backend.last_error()
        assert position >= 0.05
        assert tracks > 0

        backend.seek(1.0)
        seek_deadline = time.monotonic() + 3.0
        seek_position = 0.0
        while time.monotonic() < seek_deadline:
            seek_position = backend.position()
            if seek_position >= 0.8:
                break
            if backend.state() is PlaybackState.ERROR:
                break
            time.sleep(0.02)
        assert backend.state() is not PlaybackState.ERROR
        assert seek_position >= 0.8
    finally:
        backend.close()
        proxy.stop()
        _stop_server(server, thread)


@pytest.mark.media
@pytest.mark.skipif(
    not ctypes.util.find_library("vlc") or not shutil.which("ffmpeg"),
    reason="libVLC/FFmpeg unavailable")
def test_libvlc_reports_error_when_proxy_dies_before_open(tmp_path):
    """Documents the lifecycle-bug mechanism: a killed proxy => libVLC ERROR."""
    fixture = _make_tone(tmp_path)
    server, thread, upstream = _range_media_server(fixture)
    proxy = YouTubeMediaProxy()
    backend = LibVLCBackend(
        _HeadlessSurface(), runtime_options=("--aout=dummy", "--vout=dummy"))
    try:
        media = proxy.start(upstream)
        proxy.stop()  # MPCASU's old cleanup killed the transport pre-open
        backend.open_source(media)
        backend.play()
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline:
            if backend.state() is PlaybackState.ERROR:
                break
            time.sleep(0.02)
        assert backend.state() is PlaybackState.ERROR
        assert "libVLC" in backend.last_error()
    finally:
        backend.close()
        proxy.stop()
        _stop_server(server, thread)
