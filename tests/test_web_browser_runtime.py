from __future__ import annotations

import functools
import http.server
import importlib.util
import os
import shutil
import subprocess
import threading
from pathlib import Path

import numpy as np
import pytest

from casu.native_v2 import (
    ChunkType, NativeChunk, SubtitlePacket, encode_audio_block,
    encode_bitmap_subtitle, encode_chapter_table, encode_format_change, encode_key_state,
    encode_subtitle_packet, write_native_v2,
)
from casu.strict import canonical_frame
from web_casu import MPCASUWebServer, WebPlayerHandler


pytestmark = pytest.mark.media


def _write_multitrack_fixture(path):
    black = canonical_frame(np.zeros((2, 6), dtype=np.uint8),
                            pixel_format="rgb24", source_shape=(2, 2))
    white = canonical_frame(np.full((2, 6), 255, dtype=np.uint8),
                            pixel_format="rgb24", source_shape=(2, 2))
    wide = canonical_frame(np.full((1, 9), 80, dtype=np.uint8),
                           pixel_format="rgb24", source_shape=(1, 3))
    streams = [
        {"stream_id": 1, "type": "video", "title": "Black",
         "time_base": [1, 1000],
         "frame_timeline": [{"pts": 0, "duration_pts": 500},
                            {"pts": 500, "duration_pts": 500}]},
        {"stream_id": 2, "type": "video", "title": "White",
         "time_base": [1, 1000],
         "frame_timeline": [{"pts": 0, "duration_pts": 1000}]},
        {"stream_id": 3, "type": "audio", "language": "de",
         "time_base": [1, 1000], "sample_rate": 1000, "channels": 1},
        {"stream_id": 4, "type": "audio", "language": "en",
         "time_base": [1, 1000], "sample_rate": 1000, "channels": 1},
        {"stream_id": 5, "type": "subtitle", "language": "de",
         "time_base": [1, 1000]},
        {"stream_id": 6, "type": "subtitle", "language": "en",
         "time_base": [1, 1000]},
    ]

    def audio(value):
        return encode_audio_block(
            pcm=np.full(1000, value, dtype="<i2").tobytes(), pts=0,
            time_base_num=1, time_base_den=1000, sample_rate=1000,
            channels=1, sample_count=1000)

    bitmap = encode_bitmap_subtitle(
        start_pts=0, end_pts=1000, canvas_width=2, canvas_height=2,
        x=0, y=0, width=1, height=1, rgba=bytes((255, 0, 0, 255)))
    write_native_v2(path, {"format": "CASUNAT2", "version": 2,
                           "streams": streams}, [
        NativeChunk(ChunkType.VIDEO_KEY_STATE, 1, 0, encode_key_state(black)),
        NativeChunk(ChunkType.VIDEO_FORMAT_CHANGE, 1, 500,
                    encode_format_change(wide)),
        NativeChunk(ChunkType.VIDEO_KEY_STATE, 1, 500, encode_key_state(wide)),
        NativeChunk(ChunkType.VIDEO_KEY_STATE, 2, 0, encode_key_state(white)),
        NativeChunk(ChunkType.AUDIO_BLOCK, 3, 0, audio(100)),
        NativeChunk(ChunkType.AUDIO_BLOCK, 4, 0, audio(200)),
        NativeChunk(ChunkType.SUBTITLE_PACKET, 5, 0,
                    encode_subtitle_packet(SubtitlePacket(
                        0, 1000, "Hallo", "de"))),
        NativeChunk(ChunkType.SUBTITLE_BITMAP, 6, 0, bitmap),
        NativeChunk(ChunkType.CHAPTER_TABLE, 0, 0, encode_chapter_table([
            {"start_pts": 0, "end_pts": 1_000_000_000, "title": "Intro"}
        ])),
    ])


@pytest.mark.skipif(not shutil.which("chromium-browser"),
                    reason="Chromium browser unavailable")
def test_chromium_decodes_and_switches_native_tracks_and_bitmap(tmp_path):
    repository = Path(__file__).resolve().parents[1]
    shutil.copytree(repository / "web", tmp_path / "web")
    fixture = tmp_path / "multitrack.casu"
    _write_multitrack_fixture(fixture)
    handler = functools.partial(WebPlayerHandler, directory=str(tmp_path))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = (f"http://127.0.0.1:{server.server_address[1]}/web/"
               "native-smoke.html?file=../../multitrack.casu")
        headless_environment = os.environ.copy()
        headless_environment.pop("DISPLAY", None)
        result = subprocess.run([
            shutil.which("chromium-browser"), "--headless", "--disable-gpu",
            "--no-sandbox", "--disable-background-networking",
            "--disable-component-update", "--disable-sync",
            "--metrics-recording-only",
            f"--user-data-dir={tmp_path / 'chromium-profile'}",
            "--virtual-time-budget=10000", "--dump-dom", url,
        ], capture_output=True, text=True, timeout=45, check=False,
           env=headless_environment)
        assert result.returncode == 0, result.stderr[-2000:]
        assert ("PASS frames=1 audio=true subtitles=0 bitmaps=1 chapters=1 "
                "tracks=2/2/2 duration=1.000") in result.stdout
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.skipif(not shutil.which("chromium-browser") or not shutil.which("ffmpeg")
                    or not importlib.util.find_spec("playwright"),
                    reason="Chromium/FFmpeg/Playwright unavailable")
def test_chromium_plays_ffmpeg_fallback_for_non_browser_container(tmp_path):
    repository = Path(__file__).resolve().parents[1]
    shutil.copytree(repository / "web", tmp_path / "web")
    fixture = tmp_path / "legacy.nut"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
        "testsrc2=size=64x48:rate=5:duration=0.4", "-f", "lavfi", "-i",
        "sine=frequency=440:sample_rate=8000:duration=0.4", "-c:v", "rawvideo",
        "-c:a", "pcm_s16le", "-y", str(fixture),
    ], check=True)
    handler = functools.partial(WebPlayerHandler, directory=str(tmp_path))
    server = MPCASUWebServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/web/"
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=shutil.which("chromium-browser"), headless=True,
                args=["--no-sandbox", "--disable-gpu",
                      "--disable-background-networking",
                      "--autoplay-policy=no-user-gesture-required"])
            try:
                page = browser.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=10_000)
                page.set_input_files("#file-input", {
                    "name": "legacy.nut", "mimeType": "application/octet-stream",
                    "buffer": fixture.read_bytes(),
                })
                page.wait_for_function("state.items.length === 1", timeout=5_000)
                page.locator("#format-badge").filter(
                    has_text="AUTOMATIC FALLBACK").wait_for(timeout=10_000)
                dimensions = page.locator("#media").evaluate(
                    "node => [node.videoWidth, node.videoHeight, node.duration]")
                assert dimensions[0:2] == [64, 48]
                assert dimensions[2] > 0
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.skipif(not shutil.which("chromium-browser") or not shutil.which("ffmpeg")
                    or not importlib.util.find_spec("playwright"),
                    reason="Chromium/FFmpeg/Playwright unavailable")
def test_chromium_web_app_handles_srt_urls_and_queue_indices(tmp_path):
    repository = Path(__file__).resolve().parents[1]
    video = tmp_path / "clip.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
        "color=c=black:size=64x48:rate=5:duration=1", "-c:v", "libx264",
        "-pix_fmt", "yuv420p", "-y", str(video),
    ], check=True)
    subtitle = tmp_path / "clip.de.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:00,900\nHallo Web\n",
                        encoding="utf-8")
    handler = functools.partial(WebPlayerHandler, directory=str(repository))
    server = MPCASUWebServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/web/"
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=shutil.which("chromium-browser"), headless=True,
                args=["--no-sandbox", "--disable-gpu",
                      "--disable-background-networking",
                      "--autoplay-policy=no-user-gesture-required"])
            try:
                page = browser.new_page()
                page_errors = []
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.goto(url, wait_until="domcontentloaded", timeout=10_000)
                assert page.evaluate(
                    "youtubeId('https://www.youtube.com/watch?v=dQw4w9WgXcQ')") == "dQw4w9WgXcQ"
                assert page.evaluate(
                    "youtubeId('https://notyoutube.com/watch?v=dQw4w9WgXcQ')") is None
                assert page.evaluate(
                    "localFileRole(new File([new TextEncoder().encode('CASUNAT2payload')], 'renamed.mp4'))"
                ) == "casu"
                assert page.evaluate(
                    "localFileRole(new File(['<tv/>'], 'guide.xmltv'))"
                ) == "epg"
                with pytest.raises(Exception, match="supported network URL"):
                    page.evaluate("networkUrl('javascript:alert(1)')")
                with pytest.raises(Exception, match="8 MiB safety limit"):
                    page.evaluate("addPlaylist(new File([new Uint8Array(MAX_PLAYLIST_BYTES+1)],'huge.m3u'),new Map(),new Set())")
                epg = page.evaluate("""async () => {
                    const stamp = (date) => {
                      const p = n => String(n).padStart(2,'0');
                      return `${date.getUTCFullYear()}${p(date.getUTCMonth()+1)}${p(date.getUTCDate())}${p(date.getUTCHours())}${p(date.getUTCMinutes())}${p(date.getUTCSeconds())} +0000`;
                    };
                    const now = Date.now(), start = new Date(now-60000), stop = new Date(now+3600000);
                    const original = addItem; addItem = item => { state.items.push(item); return item; };
                    try {
                      await addPlaylist(new File(['#EXTM3U\\n#EXTINF:-1 tvg-id="news" group-title="News",News HD\\nhttps://example.test/live.m3u8\\n'],'channels.m3u'),new Map(),new Set());
                    } finally { addItem = original; }
                    await addEpg(new File([`<tv><channel id="news"><display-name>News HD</display-name></channel><programme channel="news" start="${stamp(start)}" stop="${stamp(stop)}"><title>Live bulletin</title><desc>Headlines</desc></programme></tv>`],'guide.xmltv'));
                    state.index=0; refreshEpg(); renderEpgDialog();
                    return {id:state.items[0].epgId,title:document.querySelector('#epg-now').textContent,cards:document.querySelectorAll('.epg-channel').length};
                }""")
                assert epg == {"id": "news", "title": "Live bulletin", "cards": 1}
                page.evaluate("state.items=[];state.index=-1;state.selected=-1;renderQueue();refreshEpg()")
                page.set_input_files("#file-input", [
                    {"name": "clip.mp4", "mimeType": "video/mp4",
                     "buffer": video.read_bytes()},
                    {"name": "clip.de.srt", "mimeType": "application/x-subrip",
                     "buffer": subtitle.read_bytes()},
                ])
                page.wait_for_timeout(1000)
                snapshot = page.evaluate("() => ({count:state.items.length,hidden:document.querySelector('#subtitle-track').hidden,options:document.querySelector('#subtitle-track').options.length,tracks:document.querySelectorAll('track[data-mpcasu]').length,urls:state.items.map(item=>(item.trackUrls||[]).length),subs:state.items.map(item=>(item.subtitleFiles||[]).map(file=>file.name)),toast:document.querySelector('#toast').textContent})")
                assert snapshot["count"] == 1 and not snapshot["hidden"], (snapshot, page_errors)
                page.select_option("#subtitle-track", "0")
                page.wait_for_function(
                    "() => document.querySelector('#media').textTracks[0]?.cues?.length === 1",
                    timeout=5_000)
                assert page.locator("#media").evaluate(
                    "node => node.textTracks[0].cues[0].text") == "Hallo Web"
                page.evaluate("state.items=[{title:'A',url:'https://example.test/a'},{title:'B',url:'https://example.test/b'}];state.index=1;state.selected=0;renderQueue()")
                page.click("#remove")
                assert page.evaluate("[state.items.length,state.index,state.items[state.index].title]") == [1, 0, "B"]
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
