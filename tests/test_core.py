# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
import json
import os
import shutil
from pathlib import Path

import pytest

from casu.core import CasuError, analyze, play, resolve_casu_source, rle
from casu.schema import validate_manifest
from casu.scheduler import CasuScheduler
from mpcasu_backend import LibVLCBackend
from mpcasu_playback import ControllerState, PlaybackController
from mpcasu_player import presentation_mode


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
    assert manifest["video"]["spatial_analysis"]["tile_grid"]
    assert 0.0 <= manifest["video"]["spatial_analysis"]["mean_changed_tile_ratio"] <= 1.0


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


def test_manifest_rejects_inconsistent_segment_duration_and_state():
    manifest = {
        "format": {"magic": "MPCASU\\0"},
        "casu": {"name": "CASU", "container_extension": ".casu"},
        "source": {"filename": "sample.mp4", "duration_s": 2},
        "video": {"segments": [{"start_s": 0, "end_s": 1, "duration_s": 0.5, "state": 7}]},
        "integrity": {"timestamps_are_source_of_truth": True},
    }
    errors = validate_manifest(manifest)
    assert any("duration_s must equal" in error for error in errors)
    assert any("state must be a non-empty string" in error for error in errors)


def test_manifest_rejects_nonfinite_deadline():
    manifest = {
        "format": {"magic": "MPCASU\\0"},
        "casu": {"name": "CASU", "container_extension": ".casu"},
        "source": {"filename": "sample.mp4", "duration_s": 2},
        "audio": {"segments": [{"start_s": 0, "end_s": 1, "duration_s": 1, "state": "active", "deadline_s": "NaN"}]},
        "integrity": {"timestamps_are_source_of_truth": True},
    }
    assert any("deadline_s must be finite" in error for error in validate_manifest(manifest))


def test_analysis_rejects_invalid_fps():
    with pytest.raises(CasuError, match="analysis FPS"):
        analyze(VIDEO, analysis_fps=0)


@pytest.mark.parametrize("value", [None, [], {"source": []}, {"source": {}, "casu": []}])
def test_manifest_validator_fails_closed_for_malformed_shapes(value):
    errors = validate_manifest(value)
    assert errors


def test_converter_rejects_nested_casu_input(tmp_path):
    source = tmp_path / "already.casu"
    source.write_text("{}", encoding="utf-8")
    with pytest.raises(CasuError, match="already a CASU manifest"):
        analyze(source)


def test_play_rejects_malformed_casu_before_launch(tmp_path):
    source = tmp_path / "broken.casu"
    source.write_text("{}", encoding="utf-8")
    with pytest.raises(CasuError, match="invalid CASU manifest"):
        play(source)


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


def test_libvlc_backend_source_capability_detection():
    assert LibVLCBackend.supports("https://example.invalid/video.m3u8")
    assert LibVLCBackend.supports("rtsp://example.invalid/live")
    assert not LibVLCBackend.supports("gopher://example.invalid/media")


def test_casu_scheduler_returns_deterministic_state():
    scheduler = CasuScheduler.from_manifest({"video": {"segments": [
        {"start_s": 0, "end_s": 1, "state": "static"},
        {"start_s": 1, "end_s": 2, "state": "motion"},
    ]}})
    assert scheduler.state_at(0.5).state == "static"
    assert scheduler.summary(1.5)["active_state"] == "motion"
    assert scheduler.state_at(2.0) is None


class _FakePlaybackBackend:
    def __init__(self):
        self.calls = []
        self._position = 0.0

    def play(self): self.calls.append("play")
    def pause(self): self.calls.append("pause")
    def resume(self): self.calls.append("resume")
    def stop(self): self.calls.append("stop")
    def seek(self, seconds): self.calls.append(("seek", seconds)); self._position = seconds
    def position(self): return self._position
    def duration(self): return 12.0
    def close(self): self.calls.append("close")


def test_playback_controller_owns_transport_state():
    backend = _FakePlaybackBackend()
    controller = PlaybackController()
    controller.attach(backend, "sample.mp4")
    assert controller.state is ControllerState.READY
    controller.play()
    assert controller.state is ControllerState.PLAYING
    controller.pause_or_resume()
    assert controller.state is ControllerState.PAUSED
    controller.pause_or_resume()
    controller.seek(3.5)
    controller.stop()
    controller.close()
    assert backend.calls == ["play", "pause", "resume", ("seek", 3.5), "stop", "close"]
    assert controller.state is ControllerState.EMPTY


def test_player_runtime_does_not_launch_external_player():
    source = (Path(__file__).resolve().parents[1] / "mpcasu_player.py").read_text(encoding="utf-8").lower()
    assert "ffplay" not in source
    assert "vlc.exe" not in source


def test_presentation_mode_is_stream_derived():
    assert presentation_mode({"streams": [{"codec_type": "video"}, {"codec_type": "audio"}]}) == "VIDEO"
    assert presentation_mode({"streams": [{"codec_type": "audio"}]}) == "AUDIO"
    assert presentation_mode({"streams": []}) == "ERROR"
