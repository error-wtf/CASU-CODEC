from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from casu.thumbnail import thumbnail_for
from casu.native_v2 import ChunkType, NativeChunk, encode_attachment, write_native_v2


VIDEO = Path(__file__).resolve().parents[1] / "test_media/lino_lol_test_pattern.mp4"


def test_thumbnail_missing_and_nonvideo_fail_closed(tmp_path):
    assert thumbnail_for(tmp_path / "missing", tmp_path / "cache") is None
    source = tmp_path / "not-video.bin"; source.write_bytes(b"not video")
    assert thumbnail_for(source, tmp_path / "cache") is None
    assert not list((tmp_path / "cache").glob(".*"))


@pytest.mark.media
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg unavailable")
def test_thumbnail_uses_native_cover_attachment(tmp_path):
    image = subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
        "color=c=red:size=16x12", "-frames:v", "1", "-f", "image2",
        "-vcodec", "png", "pipe:1",
    ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
    native = write_native_v2(tmp_path / "album.casu", {
        "format": "CASUNAT2", "version": 2,
        "streams": [{"stream_id": 1, "type": "attachment", "role": "cover-art"}],
    }, [NativeChunk(ChunkType.ATTACHMENT, 1, 0,
                    encode_attachment("cover.png", "image/png", image,
                                      role="cover-art"))])
    thumbnail = thumbnail_for(native, tmp_path / "cache")
    assert thumbnail is not None
    assert thumbnail.read_bytes().startswith(b"P6")


@pytest.mark.media
@pytest.mark.skipif(not VIDEO.is_file() or not shutil.which("ffmpeg"),
                    reason="reference video/ffmpeg unavailable")
def test_thumbnail_decodes_real_video_and_reuses_content_versioned_cache(tmp_path):
    first = thumbnail_for(VIDEO, tmp_path / "cache")
    second = thumbnail_for(VIDEO, tmp_path / "cache")
    assert first is not None and first == second
    assert first.read_bytes().startswith(b"P6")
    assert first.stat().st_size < 4 * 1024 * 1024
