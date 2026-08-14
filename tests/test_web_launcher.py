from __future__ import annotations

import functools
import http.server
import io
import json
import shutil
import subprocess
import threading
import urllib.request
import urllib.error
from pathlib import Path

import pytest

from web_casu import (MPCASUWebServer, TranscodeStore, WebPlayerError,
                        WebPlayerHandler, _redacted_location, main,
                        resolve_web_root)
from casu.native_v2 import convert_media_to_native_v2


def test_web_launcher_check_uses_complete_assets(capsys):
    root = Path(__file__).resolve().parents[1] / "web"
    assert resolve_web_root(root) == root.resolve()
    assert main(["--check", "--web-root", str(root)]) == 0
    assert "assets verified" in capsys.readouterr().out


def test_web_launcher_serves_player_with_security_headers():
    root = Path(__file__).resolve().parents[1] / "web"
    handler = functools.partial(WebPlayerHandler, directory=str(root.parent))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_address[1]}/web/", timeout=2) as response:
            body = response.read().decode("utf-8")
            assert response.headers["X-Content-Type-Options"] == "nosniff"
            assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"
            assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
        assert "MPCASU Web Player" in body
        with urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_address[1]}"
                "/assets/mpcasu_player_icon.png", timeout=2) as response:
            assert response.status == 200
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def test_web_launcher_rejects_dns_rebinding_host_and_cross_origin_write():
    root = Path(__file__).resolve().parents[1]
    handler = functools.partial(WebPlayerHandler, directory=str(root))
    server = MPCASUWebServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        origin = f"http://127.0.0.1:{server.server_address[1]}"
        bad_host = urllib.request.Request(origin + "/web/", headers={"Host": "attacker.test"})
        with pytest.raises(urllib.error.HTTPError) as rejected:
            urllib.request.urlopen(bad_host, timeout=2)
        assert rejected.value.code == 421
        cross_site = urllib.request.Request(
            origin + "/api/transcode-url", data=b'{}', method="POST",
            headers={"Content-Type": "application/json",
                     "Origin": "https://attacker.test",
                     "Sec-Fetch-Site": "cross-site"})
        with pytest.raises(urllib.error.HTTPError) as rejected:
            urllib.request.urlopen(cross_site, timeout=2)
        assert rejected.value.code == 403
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def test_web_launcher_proxies_bounded_http_epg_without_browser_cors(tmp_path):
    guide = (b'<?xml version="1.0"?><tv><channel id="news">'
             b'<display-name>News</display-name></channel></tv>')
    (tmp_path / "guide.xml").write_bytes(guide)
    source_handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                       directory=str(tmp_path))
    source_server = http.server.ThreadingHTTPServer(("127.0.0.1", 0),
                                                     source_handler)
    source_thread = threading.Thread(target=source_server.serve_forever,
                                     daemon=True); source_thread.start()
    root = Path(__file__).resolve().parents[1]
    player_handler = functools.partial(WebPlayerHandler, directory=str(root))
    player_server = MPCASUWebServer(("127.0.0.1", 0), player_handler)
    player_thread = threading.Thread(target=player_server.serve_forever,
                                     daemon=True); player_thread.start()
    try:
        source_url = (f"http://127.0.0.1:{source_server.server_address[1]}"
                      "/guide.xml")
        origin = f"http://127.0.0.1:{player_server.server_address[1]}"
        request = urllib.request.Request(
            origin + "/api/catalog-url",
            data=json.dumps({"url": source_url}).encode(), method="POST",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.headers["Content-Type"] == "application/octet-stream"
            assert response.read() == guide
        rejected = urllib.request.Request(
            origin + "/api/catalog-url",
            data=json.dumps({"url": "file:///etc/passwd"}).encode(),
            method="POST", headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(rejected, timeout=5)
        assert error.value.code == 400
    finally:
        player_server.shutdown(); player_server.server_close()
        source_server.shutdown(); source_server.server_close()
        player_thread.join(timeout=2); source_thread.join(timeout=2)


@pytest.mark.media
@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg unavailable")
def test_web_launcher_transcodes_non_browser_ffv1_pcm_to_mp4(tmp_path):
    source = tmp_path / "legacy.mkv"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
        "testsrc2=size=64x48:rate=5:duration=0.4", "-f", "lavfi", "-i",
        "sine=frequency=440:sample_rate=8000:duration=0.4", "-c:v", "ffv1",
        "-c:a", "pcm_s16le", "-y", str(source),
    ], check=True)
    root = Path(__file__).resolve().parents[1]
    handler = functools.partial(WebPlayerHandler, directory=str(root))
    server = MPCASUWebServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        origin = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            origin + "/api/transcode-file", data=source.read_bytes(),
            headers={"Content-Type": "application/octet-stream",
                     "X-MPCASU-Filename": "legacy.mkv"}, method="POST")
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read())
        assert payload["kind"] == "video"
        with urllib.request.urlopen(origin + payload["url"], timeout=5) as response:
            assert response.headers["Content-Type"] == "video/mp4"
            assert response.headers["Accept-Ranges"] == "bytes"
            restored = response.read()
        assert restored[4:8] == b"ftyp"
        range_request = urllib.request.Request(
            origin + payload["url"], headers={"Range": "bytes=4-7"})
        with urllib.request.urlopen(range_request, timeout=5) as response:
            assert response.status == 206
            assert response.headers["Content-Range"].startswith("bytes 4-7/")
            assert response.read() == b"ftyp"
        output = tmp_path / "browser.mp4"
        output.write_bytes(restored)
        probe = json.loads(subprocess.run([
            "ffprobe", "-v", "error", "-show_streams", "-of", "json",
            str(output),
        ], check=True, capture_output=True, text=True).stdout)
        codecs = {(item["codec_type"], item["codec_name"])
                  for item in probe["streams"]}
        assert ("video", "h264") in codecs
        assert ("audio", "aac") in codecs
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


@pytest.mark.media
@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg unavailable")
def test_web_fallback_exports_renamed_casunat2_automatically(tmp_path):
    source = tmp_path / "source.mkv"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
        "testsrc2=size=32x24:rate=4:duration=0.5", "-f", "lavfi", "-i",
        "sine=frequency=330:sample_rate=8000:duration=0.5", "-c:v", "ffv1",
        "-c:a", "pcm_s16le", "-y", str(source),
    ], check=True)
    native = tmp_path / "renamed-as-video.mp4"
    convert_media_to_native_v2(source, native)
    store = TranscodeStore()
    try:
        token, kind = store.transcode_upload(
            io.BytesIO(native.read_bytes()), native.stat().st_size, native.name,
            "mp4")
        record = store.get(token)
        assert kind == "video" and record["content_type"] == "video/mp4"
        probe = json.loads(subprocess.run([
            "ffprobe", "-v", "error", "-show_streams", "-of", "json",
            str(record["path"]),
        ], check=True, capture_output=True, text=True).stdout)
        assert {item["codec_type"] for item in probe["streams"]} >= {"video", "audio"}
    finally:
        store.close()


def test_web_transcoder_rejects_local_and_pseudo_protocol_urls():
    store = TranscodeStore()
    try:
        for source in ("file:///etc/passwd", "concat:http://one|http://two",
                       "data:text/plain,secret", "relative.mkv"):
            with pytest.raises(WebPlayerError, match="network media URLs"):
                store.register_url(source)
    finally:
        store.close()


def test_web_transcoder_redacts_url_credentials():
    assert (_redacted_location("https://user:secret@example.test/media.mkv?x=1") ==
            "https://example.test/media.mkv?x=1")


def test_interrupted_web_upload_removes_partial_file():
    store = TranscodeStore()
    try:
        with pytest.raises(WebPlayerError, match="ended before"):
            store.transcode_upload(io.BytesIO(b"short"), 20, "broken.mkv")
        assert list(store.root.iterdir()) == []
    finally:
        store.close()


@pytest.mark.media
@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg unavailable")
def test_web_launcher_streams_finite_network_source_through_browser_fallback(tmp_path):
    source = tmp_path / "network.mkv"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
        "testsrc2=size=48x32:rate=5:duration=0.4", "-c:v", "ffv1", "-y",
        str(source),
    ], check=True)
    source_handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                       directory=str(tmp_path))
    source_server = http.server.ThreadingHTTPServer(("127.0.0.1", 0),
                                                     source_handler)
    source_thread = threading.Thread(target=source_server.serve_forever,
                                     daemon=True)
    source_thread.start()
    root = Path(__file__).resolve().parents[1]
    player_handler = functools.partial(WebPlayerHandler, directory=str(root))
    player_server = MPCASUWebServer(("127.0.0.1", 0), player_handler)
    player_thread = threading.Thread(target=player_server.serve_forever,
                                     daemon=True)
    player_thread.start()
    try:
        source_url = (f"http://127.0.0.1:{source_server.server_address[1]}/"
                      f"{source.name}")
        origin = f"http://127.0.0.1:{player_server.server_address[1]}"
        request = urllib.request.Request(
            origin + "/api/transcode-url",
            data=json.dumps({"url": source_url, "target": "webm"}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read())
        with urllib.request.urlopen(origin + payload["url"], timeout=15) as response:
            assert response.headers["Content-Type"] == "video/webm"
            restored = response.read()
        output = tmp_path / "network-browser.webm"
        output.write_bytes(restored)
        probe = json.loads(subprocess.run([
            "ffprobe", "-v", "error", "-show_streams", "-of", "json",
            str(output),
        ], check=True, capture_output=True, text=True).stdout)
        assert any(item["codec_type"] == "video"
                   and item["codec_name"] == "vp9" for item in probe["streams"])
    finally:
        player_server.shutdown(); player_server.server_close()
        source_server.shutdown(); source_server.server_close()
        player_thread.join(timeout=2); source_thread.join(timeout=2)
