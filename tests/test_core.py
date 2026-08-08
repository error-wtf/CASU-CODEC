# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
import json
import os
import shutil
from pathlib import Path

import pytest

from casu.core import CasuCancelled, CasuError, analyze, play, resolve_casu_source, rle
from casu.schema import validate_manifest
from casu.scheduler import CasuScheduler
from casu.native import NativeCasuError, read_native, write_native
from casu.tiles import (TileStateError, compare_tile_frames, state_map_from_frames,
                        tile_regions)
from casu.cli import atomic_write_text
from casu.cli import main as casu_cli_main
from mpcasu_backend import LibVLCBackend
from mpcasu_playback import ControllerState, PlaybackController
from mpcasu_player import presentation_mode


VIDEO = Path(os.environ.get("CASU_TEST_VIDEO", "test_media/lino_lol_test_pattern.mp4"))
if not VIDEO.is_absolute():
    VIDEO = Path(__file__).resolve().parents[1] / VIDEO
AUDIO = Path(os.environ.get("CASU_TEST_AUDIO", "test_media/lino_casu_error.mp3"))
if not AUDIO.is_absolute():
    AUDIO = Path(__file__).resolve().parents[1] / AUDIO


@pytest.mark.media
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
    assert manifest["video"]["spatial_analysis"]["strict_pixel_identical_available"] is False
    assert manifest["video"]["segments"][0]["segment_id"].startswith("video-")
    assert manifest["audio"]["segments"][0]["segment_id"].startswith("audio-")
    assert manifest["seek_index"]["native_key_states"] is False
    assert manifest["seek_index"]["entries"]


def test_manifest_json_roundtrip(tmp_path):
    payload = {"state": "HOLD", "start_s": 0.0, "end_s": 1.0}
    target = tmp_path / "state.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    assert json.loads(target.read_text(encoding="utf-8")) == payload


def test_cli_atomic_write_text_replaces_destination(tmp_path):
    target = tmp_path / "report.json"
    target.write_text("old", encoding="utf-8")
    atomic_write_text(target, "new\\n")
    assert target.read_text(encoding="utf-8") == "new\\n"
    assert not list(tmp_path.glob(".report.json.*"))


def test_cli_refuses_output_equal_to_source(tmp_path, monkeypatch):
    source = tmp_path / "source.bin"
    source.write_bytes(b"source")
    monkeypatch.setattr("sys.argv", ["casu", "analyze", str(source), "-o", str(source)])
    monkeypatch.setattr("casu.cli.analyze", lambda *_args: {"source": {"duration_s": 1}})
    assert casu_cli_main() == 2
    assert source.read_bytes() == b"source"


def test_cli_convert_supports_multiple_inputs_and_reports_failures(tmp_path, monkeypatch, capsys):
    first = tmp_path / "one.mp4"; second = tmp_path / "two.mp4"
    first.write_bytes(b"one"); second.write_bytes(b"two")
    def fake_analyze(path, *_args):
        if path.name == "two.mp4":
            raise CasuError("unsupported fixture")
        return {"source": {"duration_s": 1}, "video": {"segments": []}, "audio": {"segments": []}}
    monkeypatch.setattr("casu.cli.analyze", fake_analyze)
    output_dir = tmp_path / "out"
    monkeypatch.setattr("sys.argv", ["casu", "convert", str(first), str(second), "-o", str(output_dir)])
    assert casu_cli_main() == 1
    report = json.loads(capsys.readouterr().out)
    assert [item["status"] for item in report["files"]] == ["converted", "failed"]
    assert (output_dir / "one.casu").is_file()


def test_cli_convert_expands_directories_and_writes_report(tmp_path, monkeypatch, capsys):
    source_dir = tmp_path / "sources"; source_dir.mkdir()
    source = source_dir / "clip.mp4"; source.write_bytes(b"clip")
    output_dir = tmp_path / "out"
    report_path = tmp_path / "batch.json"
    monkeypatch.setattr("casu.cli.analyze", lambda *_args: {
        "source": {"duration_s": 2}, "video": {"segments": []}, "audio": {"segments": []}
    })
    monkeypatch.setattr("sys.argv", ["casu", "convert", str(source_dir), "-o", str(output_dir), "--report", str(report_path)])
    assert casu_cli_main() == 0
    assert (output_dir / "clip.casu").is_file()
    assert json.loads(report_path.read_text(encoding="utf-8"))["files"][0]["status"] == "converted"


def test_cli_pack_uses_native_writer(tmp_path, monkeypatch, capsys):
    source = tmp_path / "clip.mp4"; source.write_bytes(b"clip")
    target = tmp_path / "clip.casu"
    monkeypatch.setattr("casu.cli.analyze", lambda *_args: {
        "format": {"magic": "MPCASU\\0"},
        "casu": {"name": "CASU", "container_extension": ".casu", "version": "1.0.0"},
        "source": {"filename": source.name, "duration_s": 1, "size_bytes": source.stat().st_size},
        "integrity": {"timestamps_are_source_of_truth": True},
        "seek_index": {"entries": [], "native_key_states": False},
    })
    monkeypatch.setattr("casu.cli.write_native", lambda output, _source, _manifest: output)
    monkeypatch.setattr("sys.argv", ["casu", "pack", str(source), "-o", str(target)])
    assert casu_cli_main() == 0
    assert json.loads(capsys.readouterr().out)["native_version"] == 1


def test_info_output_exposes_seek_and_native_payload_status(tmp_path, monkeypatch, capsys):
    manifest = tmp_path / "sample.casu"
    manifest.write_text(json.dumps({
        "casu": {"name": "CASU", "container_extension": ".casu", "version": "1.0.0"},
        "format": {"magic": "MPCASU\\0"},
        "source": {"filename": "sample.mp4", "duration_s": 1},
        "integrity": {"timestamps_are_source_of_truth": True},
        "seek_index": {"entries": [], "native_key_states": False},
    }), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["casu", "info", str(manifest)])
    assert casu_cli_main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["seek_index_entries"] == 0
    assert output["native_payload"] is False


def test_rle_clamps_final_partial_interval_to_source_duration():
    segments = rle(["active", "active", "silence"], 0.2, end_s=0.5)
    assert segments[-1]["end_s"] == 0.5
    assert segments[-1]["duration_s"] == 0.1
    assert segments[0]["segment_id"] == "segment-000000"
    assert segments[0]["lifecycle"] == "CREATE"


def test_strict_tile_comparison_requires_exact_canonical_bytes():
    first = __import__("numpy").zeros((4, 4, 3), dtype="uint8")
    second = first.copy()
    second[0, 0, 0] = 1
    held = compare_tile_frames(first, first, tile_width=2, tile_height=2)
    changed = compare_tile_frames(first, second, tile_width=2, tile_height=2)
    assert all(item["state"] == "HOLD" for item in held)
    assert any(item["state"] == "UPDATE" for item in changed)
    assert all(item["fidelity_class"] == "LOSSLESS_REALTIME" for item in changed)


def test_state_map_contains_spatial_coordinates_and_time_bounds():
    np = __import__("numpy")
    frames = [(0.0, np.zeros((2, 4), dtype="uint8")),
              (1.0, np.zeros((2, 4), dtype="uint8"))]
    states = state_map_from_frames(frames, tile_width=2, tile_height=2)
    assert len(states) == 4
    assert {item["tile_id"] for item in states} == {"tile-00000000", "tile-00000001"}
    assert states[0]["region"]["x"] == 0
    assert states[0]["valid_until_s"] == 1.0
    assert states[0]["state"] == "UPDATE"
    assert states[2]["state"] == "HOLD"


def test_tile_primitives_fail_closed_for_noncanonical_frames():
    np = __import__("numpy")
    with pytest.raises(TileStateError):
        compare_tile_frames(np.zeros((2, 2), dtype="float32"), np.zeros((2, 2), dtype="uint8"))


def test_native_casu_roundtrip_is_standalone_and_integrity_checked(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"native payload\x00" * 100)
    manifest = {
        "format": {"magic": "MPCASU\\0"},
        "casu": {"name": "CASU", "container_extension": ".casu", "version": "1.0.0"},
        "source": {"filename": source.name, "duration_s": 1, "size_bytes": source.stat().st_size},
        "integrity": {"timestamps_are_source_of_truth": True},
        "seek_index": {"entries": [], "native_key_states": False},
    }
    native = write_native(tmp_path / "native.casu", source, manifest)
    container = read_native(native)
    assert container.payload_length == source.stat().st_size
    extracted = container.extract_payload(tmp_path / "restored.bin")
    assert extracted.read_bytes() == source.read_bytes()
    native.write_bytes(native.read_bytes()[:-1])
    with pytest.raises(NativeCasuError, match="file size|truncated|integrity"):
        read_native(native)


def test_manifest_rejects_non_hex_digest():
    manifest = {
        "casu": {"name": "CASU", "container_extension": ".casu"},
        "source": {"filename": "sample.mp4", "duration_s": 1, "sha256": "z" * 64},
        "integrity": {"timestamps_are_source_of_truth": True},
    }
    assert any("hex digest" in error for error in validate_manifest(manifest))


def test_manifest_rejects_source_filename_path_traversal():
    manifest = {
        "casu": {"name": "CASU", "container_extension": ".casu", "version": "1.0.0"},
        "source": {"filename": "../outside.mp4", "duration_s": 1},
        "integrity": {"timestamps_are_source_of_truth": True},
    }
    assert any("basename without path traversal" in error for error in validate_manifest(manifest))


def test_manifest_rejects_source_path_filename_mismatch():
    manifest = {
        "casu": {"name": "CASU", "container_extension": ".casu", "version": "1.0.0"},
        "source": {"filename": "sample.mp4", "path": "/tmp/other.mp4", "duration_s": 1},
        "integrity": {"timestamps_are_source_of_truth": True},
    }
    assert any("source.path basename must match" in error for error in validate_manifest(manifest))


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


def test_manifest_rejects_duplicate_ids_and_invalid_segment_metadata():
    manifest = {
        "format": {"magic": "MPCASU\\0"},
        "casu": {"name": "CASU", "container_extension": ".casu", "version": "1.0.0"},
        "source": {"filename": "sample.mp4", "duration_s": 2},
        "video": {"segments": [
            {"start_s": 0, "end_s": 1, "state": "static", "segment_id": "same",
             "lifecycle": "HOLD", "priority": 1, "region": {"x": 0, "y": 0, "w": 8, "h": 8}},
            {"start_s": 1, "end_s": 2, "state": "motion", "segment_id": "same",
             "lifecycle": "UNKNOWN", "priority": "high", "region": {"x": -1, "y": 0, "w": 8, "h": 8}},
        ]},
        "integrity": {"timestamps_are_source_of_truth": True},
    }
    errors = validate_manifest(manifest)
    assert any("segment_id must be unique" in error for error in errors)
    assert any("lifecycle is unsupported" in error for error in errors)
    assert any("priority must be a bounded integer" in error for error in errors)
    assert any("region.x must be a non-negative integer" in error for error in errors)


def test_manifest_rejects_unsorted_and_invalid_seek_index():
    manifest = {
        "format": {"magic": "MPCASU\\0"},
        "casu": {"name": "CASU", "container_extension": ".casu", "version": "1.0.0"},
        "source": {"filename": "sample.mp4", "duration_s": 2},
        "seek_index": {"native_key_states": "yes", "entries": [
            {"timestamp_s": 1.0, "stream": "video", "segment_id": "s1"},
            {"timestamp_s": 0.5, "stream": "unknown", "segment_id": ""},
        ]},
        "integrity": {"timestamps_are_source_of_truth": True},
    }
    errors = validate_manifest(manifest)
    assert any("native_key_states must be boolean" in error for error in errors)
    assert any("sorted by timestamp_s" in error for error in errors)
    assert any("stream is unsupported" in error for error in errors)
    assert any("segment_id is invalid" in error for error in errors)


def test_analysis_rejects_invalid_fps():
    with pytest.raises(CasuError, match="analysis FPS"):
        analyze(VIDEO, analysis_fps=0)


def test_analysis_honors_cancellation_before_decoder_start(tmp_path, monkeypatch):
    import threading
    source = tmp_path / "source.bin"
    source.write_bytes(b"source")
    monkeypatch.setattr("casu.core.ffprobe", lambda _path: {
        "streams": [{"codec_type": "video", "width": 2, "height": 2}],
        "format": {"duration": "1"},
    })
    event = threading.Event(); event.set()
    with pytest.raises(CasuCancelled, match="cancelled"):
        analyze(source, cancel=event)


def test_analysis_rejects_input_without_playable_streams(tmp_path, monkeypatch):
    source = tmp_path / "attachment.bin"
    source.write_bytes(b"not media")
    monkeypatch.setattr("casu.core.ffprobe", lambda _path: {
        "streams": [{"codec_type": "video", "disposition": {"attached_pic": 1}}],
        "format": {"duration": "0"},
    })
    with pytest.raises(CasuError, match="no playable audio or video stream"):
        analyze(source)


@pytest.mark.parametrize("value", [None, [], {"source": []}, {"source": {}, "casu": []}])
def test_manifest_validator_fails_closed_for_malformed_shapes(value):
    errors = validate_manifest(value)
    assert errors


def test_manifest_rejects_unsupported_version_and_stream_shape():
    manifest = {
        "format": {"magic": "MPCASU\\0", "schema": "99"},
        "casu": {"name": "CASU", "container_extension": ".casu", "version": "9.0.0"},
        "source": {"filename": "sample.mp4", "duration_s": 1},
        "streams": [{"codec_type": "alien", "codec_name": "x"}],
        "integrity": {"timestamps_are_source_of_truth": True},
    }
    errors = validate_manifest(manifest)
    assert any("casu.version" in error for error in errors)
    assert any("format.schema" in error for error in errors)
    assert any("codec_type" in error for error in errors)


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


@pytest.mark.media
@pytest.mark.skipif(not VIDEO.exists() or not shutil.which("ffmpeg"), reason="test video/ffmpeg unavailable")
def test_casu_manifest_resolves_original_media(tmp_path):
    manifest = analyze(VIDEO, analysis_fps=1.0)
    sidecar = tmp_path / "video.casu"
    sidecar.write_text(json.dumps(manifest), encoding="utf-8")
    assert resolve_casu_source(sidecar) == VIDEO.resolve()


@pytest.mark.media
@pytest.mark.skipif(not VIDEO.exists() or not shutil.which("ffmpeg"), reason="test video/ffmpeg unavailable")
def test_casu_manifest_rejects_changed_source_digest(tmp_path):
    manifest = analyze(VIDEO, analysis_fps=1.0)
    manifest["source"]["sha256"] = "0" * 64
    sidecar = tmp_path / "changed.casu"
    sidecar.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(CasuError, match="integrity mismatch"):
        resolve_casu_source(sidecar)


@pytest.mark.media
@pytest.mark.skipif(not VIDEO.exists() or not shutil.which("ffmpeg"), reason="test video/ffmpeg unavailable")
def test_casu_manifest_rejects_changed_source_size(tmp_path):
    manifest = analyze(VIDEO, analysis_fps=1.0)
    manifest["source"]["sha256"] = None
    manifest["source"]["size_bytes"] += 1
    sidecar = tmp_path / "changed-size.casu"
    sidecar.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(CasuError, match="size mismatch"):
        resolve_casu_source(sidecar)


@pytest.mark.media
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


def test_backend_exposes_active_playback_diagnostic():
    source = Path("mpcasu_backend.py").read_text(encoding="utf-8")
    player = Path("mpcasu_player.py").read_text(encoding="utf-8")
    assert "def is_actively_playing" in source
    assert "did not enter active playback" in player


def test_backend_exposes_optional_video_track_selection():
    source = Path("mpcasu_backend.py").read_text(encoding="utf-8")
    assert "libvlc_video_get_track_count" in source
    assert "def set_video_track" in source
    assert "def video_track_descriptions" in source
    player = Path("mpcasu_player.py").read_text(encoding="utf-8")
    assert "def cycle_video_track" in player


def test_backend_maps_libvlc_media_error_state():
    source = Path("mpcasu_backend.py").read_text(encoding="utf-8")
    assert "libvlc_media_get_state" in source
    assert "media_state == 7" in source


def test_libvlc_library_candidates_are_platform_independent():
    # The backend must keep a shared-library fallback chain instead of
    # assuming a Debian x86_64 soname in its public source contract.
    source = Path("mpcasu_backend.py").read_text(encoding="utf-8")
    assert '"libvlc.so.5", "libvlc.so"' in source
    assert '"libvlc.dylib"' in source
    assert '"libvlc.dll", "libvlc-5.dll"' in source


def test_casu_backend_does_not_claim_native_payload_playback():
    source = Path("mpcasu_backend.py").read_text(encoding="utf-8")
    player = Path("mpcasu_player.py").read_text(encoding="utf-8")
    assert '"native_casu_payload": "unavailable"' in source
    assert "Native CASU manifest" not in player


def test_casu_scheduler_returns_deterministic_state():
    scheduler = CasuScheduler.from_manifest({"video": {"segments": [
        {"start_s": 0, "end_s": 1, "state": "static"},
        {"start_s": 1, "end_s": 2, "state": "motion"},
    ]}})
    assert scheduler.state_at(0.5).state == "static"
    assert scheduler.summary(1.5)["active_state"] == "motion"
    assert scheduler.state_at(2.0) is None


def test_casu_scheduler_preserves_segment_metadata_and_index_lookup():
    scheduler = CasuScheduler.from_manifest({"video": {"segments": [
        {"start_s": 0, "end_s": 1, "state": "static", "segment_id": "s0",
         "region": {"x": 0, "y": 0, "w": 16, "h": 9}, "lifecycle": "HOLD",
         "priority": 3, "deadline_s": 0.9, "reference_state": "key-0"},
        {"start_s": 1, "end_s": 2, "state": "motion", "segment_id": "s1"},
    ]}})
    assert scheduler.state_at(0.25).segment_id == "s0"
    summary = scheduler.summary(0.25)
    assert summary["active_lifecycle"] == "HOLD"
    assert summary["active_priority"] == 3
    assert summary["active_deadline_s"] == 0.9


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


def test_presentation_mode_ignores_attached_cover_art():
    assert presentation_mode({"streams": [
        {"codec_type": "video", "disposition": {"attached_pic": 1}},
        {"codec_type": "audio"},
    ]}) == "AUDIO"
