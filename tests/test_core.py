import json
import os
import shutil
from pathlib import Path

import pytest

from casu.core import CasuError, analyze, resolve_casu_source, rle
from casu.schema import validate_manifest


VIDEO = Path(os.environ.get("CASU_TEST_VIDEO", "test_media/lino_lol_test_pattern.mp4"))
if not VIDEO.is_absolute():
    VIDEO = Path(__file__).resolve().parents[1] / VIDEO
AUDIO = Path(os.environ.get("CASU_TEST_AUDIO", "test_media/lino_casu_error.mp3"))
if not AUDIO.is_absolute():
    AUDIO = Path(__file__).resolve().parents[1] / AUDIO


@pytest.mark.skipif(not VIDEO.exists() or not shutil.which("ffmpeg"), reason="test video/ffmpeg unavailable")
def test_reference_video_manifest_preserves_source_metadata(tmp_path):
    manifest = analyze(VIDEO, analysis_fps=2.0)
    assert manifest["source"]["duration_s"] > 100
    assert manifest["streams"][0]["codec_type"] == "video"
    assert manifest["streams"][1]["codec_type"] == "audio"
    assert manifest["integrity"]["timestamps_are_source_of_truth"] is True
    assert manifest["video"]["state_is_hint_only"] is True
    assert manifest["audio"]["state_is_hint_only"] is True


def test_manifest_json_roundtrip(tmp_path):
    payload = {"state": "HOLD", "start_s": 0.0, "end_s": 1.0}
    target = tmp_path / "state.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    assert json.loads(target.read_text(encoding="utf-8")) == payload


def test_rle_clamps_final_partial_interval_to_source_duration():
    segments = rle(["active", "active", "silence"], 0.2, end_s=0.5)
    assert segments[-1]["end_s"] == 0.5
    assert segments[-1]["duration_s"] == 0.1


def test_manifest_rejects_non_hex_digest():
    manifest = {
        "casu": {"name": "CASU", "container_extension": ".casu"},
        "source": {"filename": "sample.mp4", "duration_s": 1, "sha256": "z" * 64},
        "integrity": {"timestamps_are_source_of_truth": True},
    }
    assert any("hex digest" in error for error in validate_manifest(manifest))


@pytest.mark.parametrize("value", [None, [], {"source": []}, {"source": {}, "casu": []}])
def test_manifest_validator_fails_closed_for_malformed_shapes(value):
    errors = validate_manifest(value)
    assert errors


@pytest.mark.skipif(not VIDEO.exists() or not shutil.which("ffmpeg"), reason="test video/ffmpeg unavailable")
def test_casu_manifest_resolves_original_media(tmp_path):
    manifest = analyze(VIDEO, analysis_fps=1.0)
    sidecar = tmp_path / "video.casu"
    sidecar.write_text(json.dumps(manifest), encoding="utf-8")
    assert resolve_casu_source(sidecar) == VIDEO.resolve()


@pytest.mark.skipif(not VIDEO.exists() or not shutil.which("ffmpeg"), reason="test video/ffmpeg unavailable")
def test_casu_manifest_rejects_changed_source_digest(tmp_path):
    manifest = analyze(VIDEO, analysis_fps=1.0)
    manifest["source"]["sha256"] = "0" * 64
    sidecar = tmp_path / "changed.casu"
    sidecar.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(CasuError, match="integrity mismatch"):
        resolve_casu_source(sidecar)


@pytest.mark.skipif(not VIDEO.exists() or not shutil.which("ffmpeg"), reason="test video/ffmpeg unavailable")
def test_casu_manifest_rejects_changed_source_size(tmp_path):
    manifest = analyze(VIDEO, analysis_fps=1.0)
    manifest["source"]["sha256"] = None
    manifest["source"]["size_bytes"] += 1
    sidecar = tmp_path / "changed-size.casu"
    sidecar.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(CasuError, match="size mismatch"):
        resolve_casu_source(sidecar)


@pytest.mark.skipif(not AUDIO.exists() or not shutil.which("ffmpeg"), reason="test audio/ffmpeg unavailable")
def test_reference_mp3_manifest_preserves_audio_stream():
    manifest = analyze(AUDIO, analysis_fps=1.0)
    assert manifest["source"]["duration_s"] > 270
    assert any(item.get("codec_type") == "audio" and item.get("codec_name") == "mp3" for item in manifest["streams"])
    assert manifest["audio"]["segments"]
    assert manifest["integrity"]["timestamps_are_source_of_truth"] is True
