from __future__ import annotations

import io
import json
import shutil
import subprocess

import pytest

from web_casu import TranscodeStore


pytestmark = [pytest.mark.media,
              pytest.mark.skipif(not shutil.which("ffmpeg") or
                                  not shutil.which("ffprobe"),
                                  reason="FFmpeg unavailable")]


AUDIO_FORMATS = [
    (".mp3", "libmp3lame"), (".flac", "flac"), (".wma", "wmav2"),
    (".aiff", "pcm_s16be"), (".ogg", "libvorbis"), (".opus", "libopus"),
    (".m4a", "aac"),
]

VIDEO_FORMATS = [
    (".mp4", "libx264"), (".mov", "mpeg4"), (".mjpeg.avi", "mjpeg"),
    (".mkv", "libx265"), (".vp8.webm", "libvpx"),
    (".vp9.webm", "libvpx-vp9"), (".av1.mkv", "libaom-av1"),
    (".ts", "mpeg2video"), (".ffv1.mkv", "ffv1"),
]


def _probe(path):
    return json.loads(subprocess.run([
        "ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path),
    ], check=True, capture_output=True, text=True).stdout)["streams"]


@pytest.mark.parametrize("suffix,encoder", AUDIO_FORMATS)
def test_web_fallback_audio_format_matrix(tmp_path, suffix, encoder):
    source = tmp_path / f"tone{suffix}"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
        "sine=frequency=440:sample_rate=16000:duration=0.2", "-c:a", encoder,
        "-y", str(source),
    ], check=True)
    store = TranscodeStore()
    try:
        token, kind = store.transcode_upload(
            io.BytesIO(source.read_bytes()), source.stat().st_size, source.name,
            "webm")
        record = store.get(token)
        assert kind == "audio" and record["content_type"] == "audio/webm"
        streams = _probe(record["path"])
        assert [(item["codec_type"], item["codec_name"]) for item in streams
                if item["codec_type"] == "audio"] == [("audio", "opus")]
    finally:
        store.close()


@pytest.mark.parametrize("suffix,encoder", VIDEO_FORMATS)
def test_web_fallback_video_format_matrix(tmp_path, suffix, encoder):
    source = tmp_path / f"pattern{suffix}"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
        "testsrc2=size=48x32:rate=5:duration=0.2", "-c:v", encoder, "-y",
        str(source),
    ], check=True)
    store = TranscodeStore()
    try:
        token, kind = store.transcode_upload(
            io.BytesIO(source.read_bytes()), source.stat().st_size, source.name,
            "webm")
        record = store.get(token)
        assert kind == "video" and record["content_type"] == "video/webm"
        streams = _probe(record["path"])
        assert [(item["codec_type"], item["codec_name"]) for item in streams
                if item["codec_type"] == "video"] == [("video", "vp9")]
    finally:
        store.close()
