from __future__ import annotations

import shutil
import subprocess
import time

import pytest

from casu.core import ffprobe
from casu.recording import MediaRecorder, RecordingError


@pytest.mark.media
@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg unavailable")
def test_recorder_atomically_publishes_verified_all_stream_copy(tmp_path):
    source = tmp_path / "source.mkv"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
        "testsrc2=size=48x32:rate=5:duration=0.5", "-f", "lavfi", "-i",
        "sine=frequency=440:sample_rate=8000:duration=0.5", "-c:v", "ffv1",
        "-c:a", "pcm_s16le", "-y", str(source),
    ], check=True)
    output = tmp_path / "recorded.mkv"
    recorder = MediaRecorder(source, output); recorder.start()
    deadline = time.monotonic() + 5
    while recorder.active and time.monotonic() < deadline:
        time.sleep(.02)
    assert recorder.finish() == output
    assert not list(tmp_path.glob(".recorded.recording-*"))
    assert {item["codec_type"] for item in ffprobe(output)["streams"]} == {"audio", "video"}


def test_recorder_rejects_source_overwrite_and_unsupported_target(tmp_path):
    source = tmp_path / "source.mkv"; source.write_bytes(b"x")
    with pytest.raises(RecordingError, match="overwrite"):
        MediaRecorder(source, source)
    with pytest.raises(RecordingError, match="format"):
        MediaRecorder(source, tmp_path / "recording.exe")
