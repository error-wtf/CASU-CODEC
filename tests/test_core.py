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
from casu.native_v2 import (ChunkType, NativeChunk, NativeV2Error, TileStateCache,
                            decode_audio_block, encode_audio_block, encode_key_state,
                            encode_tile_update, read_native_v2, recover_native_v2, write_native_v2,
                            repair_native_v2,
                            decode_attachment, encode_attachment,
                            decode_bitmap_subtitle, encode_bitmap_subtitle,
                            SubtitlePacket, decode_chapter_table, decode_subtitle_packet,
                            encode_chapter_table, encode_subtitle_packet)
from casu.native_v2.converter import (NativeConversionError, _bitmap_canvas_size,
                                       _bounded_tags)
from casu.tiles import (TileStateError, compare_tile_frames, state_map_from_frames,
                        tile_regions)
from casu.cli import atomic_write_text
from casu.cli import main as casu_cli_main
from mpcasu_backend import (CasuBackend, LibVLCBackend,
                            LIBVLC_PLAYER_EVENT_STATES, PlaybackState)
from mpcasu_native_backend import NativeCasuBackend
from mpcasu_playback import ControllerState, PlaybackController
from mpcasu_player import MPCASUPlayer, chapter_marker_positions, presentation_mode
from casu.strict import StrictFrame, build_state_map, canonical_frame, iter_source_frames


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
    assert manifest["video"]["state_is_hint_only"] is False
    assert manifest["video"]["strict_pixel_identical_available"] is True
    assert manifest["audio"]["state_is_hint_only"] is True
    assert manifest["video"]["spatial_analysis"]["tile_grid"]
    assert manifest["video"]["spatial_analysis"]["strict_pixel_identical_available"] is True
    state_map = manifest["video"]["spatial_analysis"]["state_map"]
    assert state_map and state_map[0]["tile_id"].startswith("tile-")
    assert manifest["video"]["spatial_analysis"]["state_map_identity_scope"].startswith(
        "all active native decoded planes")
    assert manifest["video"]["segments"] == []
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
    def fake_analyze(path, *_args, **_kwargs):
        if path.name == "two.mp4":
            raise CasuError("unsupported fixture")
        return {"source": {"duration_s": 1}, "video": {"segments": []}, "audio": {"segments": []}}
    monkeypatch.setattr("casu.jobs.analyze", fake_analyze)
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
    monkeypatch.setattr("casu.jobs.analyze", lambda *_args, **_kwargs: {
        "source": {"duration_s": 2}, "video": {"segments": []}, "audio": {"segments": []}
    })
    monkeypatch.setattr("sys.argv", ["casu", "convert", str(source_dir), "-o", str(output_dir), "--report", str(report_path)])
    assert casu_cli_main() == 0
    assert (output_dir / "clip.casu").is_file()
    assert json.loads(report_path.read_text(encoding="utf-8"))["files"][0]["status"] == "converted"


def test_cli_convert_rejects_negative_retry(tmp_path, monkeypatch, capsys):
    source = tmp_path / "clip.mp4"; source.write_bytes(b"clip")
    monkeypatch.setattr("sys.argv", ["casu", "convert", str(source), "--retry", "-1"])
    assert casu_cli_main() == 2
    assert "retry count" in capsys.readouterr().out


def test_cli_convert_native_container_mode_is_explicit(tmp_path, monkeypatch, capsys):
    source = tmp_path / "clip.mp4"; source.write_bytes(b"clip")
    output_dir = tmp_path / "out"
    monkeypatch.setattr("casu.jobs.analyze", lambda *_args, **_kwargs: {
        "source": {"duration_s": 2}, "video": {"segments": []}, "audio": {"segments": []}
    })
    calls = []
    def fake_write(output, source_path, _manifest):
        calls.append((output, source_path))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"native")
        return output
    monkeypatch.setattr("casu.jobs.write_native", fake_write)
    monkeypatch.setattr("sys.argv", ["casu", "convert", str(source), "-o", str(output_dir), "--container", "native"])
    assert casu_cli_main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["container"] == "native"
    assert report["files"][0]["container"] == "native"
    assert calls and (output_dir / "clip.casu").read_bytes() == b"native"


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


def test_source_resolution_strict_detects_single_chroma_or_alpha_sample():
    np = __import__("numpy")
    y = np.zeros((4, 4), dtype="uint8")
    chroma = np.zeros((2, 2), dtype="uint8")
    previous = canonical_frame((y, chroma, chroma), pixel_format="yuv420p")
    changed_chroma = chroma.copy(); changed_chroma[1, 1] = 1
    current = canonical_frame((y, changed_chroma, chroma), pixel_format="yuv420p")
    frames = [StrictFrame(0, 1, 1, previous), StrictFrame(1, 1, 1, current)]
    states = build_state_map(frames, tile_width=4, tile_height=4)
    assert states[0]["state"] == "KEY_STATE"
    assert states[0]["fidelity"] == "SOURCE_RESOLUTION_STRICT"
    assert states[0]["valid_from_s"] == 0.0
    assert states[1]["state"] == "UPDATE"


def test_source_resolution_strict_holds_identical_multiplane_frame():
    np = __import__("numpy")
    planes = (np.zeros((2, 2), dtype="uint16"), np.ones((1, 1), dtype="uint16"),
              np.ones((1, 1), dtype="uint16"))
    frame = canonical_frame(planes, pixel_format="yuv420p10le")
    states = build_state_map([StrictFrame(10, 1, 1000, frame), StrictFrame(20, 1, 1000, frame)], tile_width=2, tile_height=2)
    assert states[1]["state"] == "HOLD"
    assert states[1]["valid_from_s"] == 0.02


@pytest.mark.media
@pytest.mark.skipif(not VIDEO.exists() or not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="test video/ffmpeg/ffprobe unavailable")
def test_source_decoder_preserves_native_yuv_planes_and_pts():
    frames = list(iter_source_frames(VIDEO, max_frames=2))
    assert len(frames) == 2
    assert frames[0].frame.pixel_format == "yuv420p"
    assert frames[0].frame.shape == (360, 640)
    assert [plane.shape for plane in frames[0].frame.planes] == [(360, 640), (180, 320), (180, 320)]
    assert frames[0].timestamp_s == 0.0
    assert frames[1].timestamp_s > frames[0].timestamp_s


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


def test_native_v2_is_segmented_standalone_and_has_byte_seek_index(tmp_path):
    target = tmp_path / "segment.casu"
    chunks = [
        NativeChunk(ChunkType.STREAM_CONFIG, 0, 0, b"video:yuv420p"),
        NativeChunk(ChunkType.VIDEO_KEY_STATE, 0, 0, b"key-state"),
        NativeChunk(ChunkType.VIDEO_TILE_UPDATE, 0, 1, b"tile-update"),
        NativeChunk(ChunkType.AUDIO_BLOCK, 1, 0, b"pcm-block"),
    ]
    write_native_v2(target, {"format": "CASUNAT2", "streams": [0, 1]}, chunks)
    container = read_native_v2(target)
    assert container.integrity_verified is True
    assert [item.chunk_type for item in container.chunks[:2]] == [ChunkType.STREAM_CONFIG, ChunkType.VIDEO_KEY_STATE]
    assert container.seek_entries
    assert container.seek_entries[0].key_state_offset > 0
    assert container.seek_entries[0].first_update_offset >= container.seek_entries[0].key_state_offset


def test_native_v2_key_state_and_tile_update_reconstruct_subsampled_planes():
    np = __import__("numpy")
    y = np.zeros((4, 8), dtype="uint8")
    u = np.zeros((2, 4), dtype="uint8")
    v = np.zeros((2, 4), dtype="uint8")
    original = canonical_frame((y, u, v), pixel_format="yuv420p", source_shape=(4, 8))
    changed_y = y.copy(); changed_y[1, 5] = 99
    changed_u = u.copy(); changed_u[0, 2] = 77
    changed = canonical_frame((changed_y, changed_u, v), pixel_format="yuv420p", source_shape=(4, 8))
    cache = TileStateCache(); cache.apply_key_state(encode_key_state(original))
    result = cache.apply_tile_update(encode_tile_update(changed, x=4, y=0, width=4, height=4))
    assert result.planes[0][1, 5] == 99
    assert result.planes[1][0, 2] == 77


def test_native_v2_recovery_points_and_reader_limits(tmp_path):
    target = tmp_path / "recoverable.casu"
    chunks = [NativeChunk(ChunkType.VIDEO_KEY_STATE, 0, i, bytes([i])) for i in range(3)]
    write_native_v2(target, {"format": "CASUNAT2"}, chunks, recovery_interval=1)
    container = read_native_v2(target)
    assert len(container.recovery_points) == 3
    assert all(point["key_state_offsets"] for point in container.recovery_points)
    with pytest.raises(NativeV2Error, match="size limit"):
        read_native_v2(target, max_file_bytes=1)


def test_native_v2_lazy_reader_keeps_payloads_on_disk(tmp_path):
    target = tmp_path / "lazy.casu"
    payload = b"x" * 100_000
    write_native_v2(target, {"format": "CASUNAT2"}, [
        NativeChunk(ChunkType.VIDEO_KEY_STATE, 1, 0, payload),
    ])
    container = read_native_v2(target, load_payloads=False)
    summary = next(chunk for chunk in container.chunks
                   if chunk.chunk_type == ChunkType.VIDEO_KEY_STATE)
    assert summary.payload == b""
    offset = container.offsets[container.chunks.index(summary)]
    loaded, _ = container.read_chunk_at(offset)
    assert loaded.payload == payload
    with target.open("r+b") as handle:
        handle.seek(offset + 28)
        value = handle.read(1)
        handle.seek(offset + 28)
        handle.write(bytes([value[0] ^ 1]))
    with pytest.raises(NativeV2Error, match="changed after verification"):
        container.read_chunk_at(offset)


def test_native_v2_recovers_last_complete_prefix_after_truncation(tmp_path):
    target = tmp_path / "interrupted.casu"
    chunks = [NativeChunk(ChunkType.VIDEO_KEY_STATE, 0, i, bytes([i])) for i in range(4)]
    write_native_v2(target, {"format": "CASUNAT2"}, chunks, recovery_interval=1)
    raw = target.read_bytes()
    with pytest.raises(NativeV2Error, match="recovery size limit"):
        recover_native_v2(target, max_file_bytes=1)
    target.write_bytes(raw[:-17])
    snapshot = recover_native_v2(target)
    assert snapshot.recovery_point["last_complete_chunk_offset"] == snapshot.complete_chunk_offset
    assert snapshot.chunks
    with pytest.raises(NativeV2Error, match="missing END|truncated"):
        read_native_v2(target)
    repaired_path = repair_native_v2(target, tmp_path / "repaired.casu")
    repaired = read_native_v2(repaired_path)
    assert repaired.integrity_verified is True
    assert repaired.manifest["recovery"]["status"] == "RECOVERED_PREFIX"


def test_native_v2_audio_block_roundtrip_preserves_pcm_and_timing():
    pcm = bytes(range(64))
    payload = encode_audio_block(pcm=pcm, pts=480, time_base_num=1, time_base_den=48000,
                                 sample_rate=48000, channels=2, channel_layout="stereo",
                                 sample_format="s16le", sample_count=16)
    block = decode_audio_block(payload)
    assert block.pcm == pcm
    assert block.pts == 480
    assert block.channel_layout == "stereo"
    assert block.sample_count == 16
    with pytest.raises(ValueError, match="PCM byte length"):
        encode_audio_block(pcm=b"short", pts=0, time_base_num=1, time_base_den=1,
                           sample_rate=48000, channels=2, sample_count=16)
    with pytest.raises(ValueError, match="timing"):
        encode_audio_block(pcm=b"", pts=0, time_base_num=0, time_base_den=1,
                           sample_rate=48000, channels=2, sample_count=0)


def test_native_v2_attachment_roundtrip_is_bounded_and_hashed():
    payload = encode_attachment("font.txt", "text/plain", b"CASU attachment",
                                role="subtitle-font")
    attachment = decode_attachment(payload)
    assert attachment.filename == "font.txt"
    assert attachment.media_type == "text/plain"
    assert attachment.data == b"CASU attachment"
    assert attachment.role == "subtitle-font"
    with pytest.raises(ValueError, match="safe basename"):
        encode_attachment("../escape.txt", "text/plain", b"bad")


def test_native_v2_metadata_is_canonical_and_bounded():
    assert _bounded_tags({"title": "CASU", "artist": "Lino"}) == {
        "artist": "Lino", "title": "CASU",
    }
    with pytest.raises(NativeConversionError, match="value exceeds"):
        _bounded_tags({"comment": "x" * 4097})
    with pytest.raises(NativeConversionError, match="count"):
        _bounded_tags({str(index): "x" for index in range(257)})


def test_native_v2_text_payloads_enforce_resource_limits():
    with pytest.raises(ValueError, match="exceeds limit"):
        encode_subtitle_packet(SubtitlePacket(0, 1, "x" * (1024 * 1024 + 1)))
    with pytest.raises(ValueError, match="chapter count"):
        encode_chapter_table([{"start_pts": 0, "end_pts": 1, "title": "x"}] * 100_001)


def test_native_v2_bitmap_subtitle_roundtrip_is_bounded_and_hashed():
    rgba = bytes([255, 0, 0, 255] * 6)
    payload = encode_bitmap_subtitle(
        start_pts=100, end_pts=900, canvas_width=10, canvas_height=8,
        x=2, y=3, width=3, height=2, rgba=rgba)
    packet = decode_bitmap_subtitle(payload)
    assert packet.rgba == rgba and packet.sha256
    canvas = packet.canvas_rgba()
    assert canvas.shape == (8, 10, 4)
    assert canvas[3:5, 2:5].tobytes() == rgba
    damaged = bytearray(payload); damaged[-1] ^= 1
    with pytest.raises(ValueError, match="invalid bitmap"):
        decode_bitmap_subtitle(bytes(damaged))
    with pytest.raises(ValueError, match="geometry"):
        encode_bitmap_subtitle(start_pts=1, end_pts=0, canvas_width=1,
                               canvas_height=1, x=0, y=0, width=1,
                               height=1, rgba=b"\0" * 4)
    with pytest.raises(ValueError, match="geometry"):
        encode_bitmap_subtitle(start_pts=0, end_pts=1, canvas_width=1_000_000,
                               canvas_height=1_000_000, x=0, y=0, width=1,
                               height=1, rgba=b"\0" * 4)


def test_bitmap_subtitle_canvas_uses_stream_geometry_and_dvd_d1_standard():
    overview = {"streams": [{"codec_type": "video", "width": 352, "height": 288,
                              "avg_frame_rate": "25/1", "disposition": {}}]}
    assert _bitmap_canvas_size({"codec_name": "dvd_subtitle"}, overview) == (720, 576)
    overview["streams"][0].update(height=240, avg_frame_rate="30000/1001")
    assert _bitmap_canvas_size({"codec_name": "dvd_subtitle"}, overview) == (720, 480)
    assert _bitmap_canvas_size({"codec_name": "xsub", "width": 640, "height": 360},
                               overview) == (640, 360)


def test_cli_verify_accepts_native_container(tmp_path, monkeypatch, capsys):
    source = tmp_path / "source.bin"
    source.write_bytes(b"payload")
    manifest = {
        "format": {"magic": "MPCASU\\0"},
        "casu": {"name": "CASU", "container_extension": ".casu", "version": "1.0.0"},
        "source": {"filename": source.name, "duration_s": 1, "size_bytes": source.stat().st_size},
        "integrity": {"timestamps_are_source_of_truth": True},
        "seek_index": {"entries": [], "native_key_states": False},
    }
    native = write_native(tmp_path / "source.casu", source, manifest)
    monkeypatch.setattr("sys.argv", ["casu", "verify", str(native)])
    assert casu_cli_main() == 0
    assert "native CASU container" in capsys.readouterr().out


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


def test_libvlc_event_codes_distinguish_eof_from_decoder_error():
    assert LIBVLC_PLAYER_EVENT_STATES[0x109] is PlaybackState.ENDED
    assert LIBVLC_PLAYER_EVENT_STATES[0x10A] is PlaybackState.ERROR
    assert 0x11B not in LIBVLC_PLAYER_EVENT_STATES


def test_backend_exposes_active_playback_diagnostic():
    backend = LibVLCBackend.__new__(LibVLCBackend)
    backend.player = object()
    backend.libvlc_media_player_is_playing = lambda _player: 1
    assert backend.is_actively_playing() is True
    backend.libvlc_media_player_is_playing = lambda _player: 0
    assert backend.is_actively_playing() is False


def test_backend_exposes_optional_video_track_selection():
    selected = []
    backend = LibVLCBackend.__new__(LibVLCBackend)
    backend.player = object(); backend._video_track_api = True
    backend.libvlc_video_get_track_count = lambda _player: 3
    backend.libvlc_video_get_track = lambda _player: 7
    backend.libvlc_video_set_track = lambda _player, value: selected.append(value) or 0
    assert backend.video_track_count() == 3
    assert backend.video_track() == 7
    backend.set_video_track(9)
    assert selected == [9]


def test_libvlc_chapter_descriptors_reflect_runtime_count():
    backend = LibVLCBackend.__new__(LibVLCBackend)
    backend.chapter_count = lambda: 2
    chapters = backend.chapter_descriptors()
    assert [item.identifier for item in chapters] == [0, 1]
    assert [item.title for item in chapters] == ["Chapter 1", "Chapter 2"]


def test_chapter_marker_positions_are_bounded_and_backend_neutral():
    from casu.media import ChapterDescriptor
    chapters = (
        ChapterDescriptor(0, -2.0, "Intro", 10.0),
        ChapterDescriptor(1, 50.0, "Middle", 70.0),
        ChapterDescriptor(2, 120.0, "Credits", 130.0),
    )
    markers = chapter_marker_positions(chapters, duration=100.0, width=500)
    assert [(item[0], item[1]) for item in markers] == [(0, 0.0), (1, 250.0),
                                                        (2, 500.0)]
    assert chapter_marker_positions(chapters, duration=0, width=500) == ()


def test_player_resets_stored_rate_for_native_audio():
    class RateButton:
        def __init__(self): self.text = None
        def configure(self, **values): self.text = values.get("text")

    player = MPCASUPlayer.__new__(MPCASUPlayer)
    player.backend = NativeCasuBackend()
    player.backend._selected_audio = 1
    player._rate = 2.0
    player.rate_button = RateButton()
    player._apply_playback_rate()
    assert player._rate == 1.0
    assert player.rate_button.text == "1×"


def test_libvlc_delay_controls_convert_milliseconds_to_microseconds():
    calls = []
    backend = LibVLCBackend.__new__(LibVLCBackend)
    backend.player = object()
    backend._audio_delay_api = backend._subtitle_delay_api = True
    backend.libvlc_audio_set_delay = lambda _player, value: calls.append(("audio", value)) or 0
    backend.libvlc_video_set_spu_delay = lambda _player, value: calls.append(("subtitle", value)) or 0
    assert backend.set_audio_delay(125.5) == 125.5
    assert backend.set_subtitle_delay(-250) == -250
    assert calls == [("audio", 125500), ("subtitle", -250000)]


def test_backend_maps_libvlc_media_error_state():
    backend = LibVLCBackend.__new__(LibVLCBackend)
    backend._media_state_api = True; backend.media = object(); backend.player = None
    backend._state = PlaybackState.READY
    backend.libvlc_media_get_state = lambda _media: 7
    assert backend.state() is PlaybackState.ERROR


def test_libvlc_library_candidates_are_platform_independent():
    linux = LibVLCBackend.library_candidates("linux")
    assert "libvlc.so.5" in linux and "libvlc.so" in linux
    assert LibVLCBackend.library_candidates("darwin") == ["libvlc.dylib"]
    assert LibVLCBackend.library_candidates("win32") == ["libvlc.dll", "libvlc-5.dll"]


def test_native_casu_backend_is_independent_from_libvlc_compatibility():
    assert issubclass(CasuBackend, LibVLCBackend)
    assert not issubclass(NativeCasuBackend, LibVLCBackend)


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


def test_legacy_playback_delegates_to_in_process_libvlc_api():
    calls = []
    backend = LibVLCBackend.__new__(LibVLCBackend)
    backend.player = object(); backend.media = None; backend._media_state_api = False
    backend._state = PlaybackState.READY
    backend.libvlc_media_player_play = lambda player: calls.append(player) or 0
    backend.libvlc_media_player_is_playing = lambda _player: 1
    backend.play()
    assert calls == [backend.player]
    assert backend.state() is PlaybackState.PLAYING


def test_presentation_mode_is_stream_derived():
    assert presentation_mode({"streams": [{"codec_type": "video"}, {"codec_type": "audio"}]}) == "VIDEO"
    assert presentation_mode({"streams": [{"codec_type": "audio"}]}) == "AUDIO"
    assert presentation_mode({"streams": []}) == "ERROR"


def test_presentation_mode_ignores_attached_cover_art():
    assert presentation_mode({"streams": [
        {"codec_type": "video", "disposition": {"attached_pic": 1}},
        {"codec_type": "audio"},
    ]}) == "AUDIO"


def test_native_v2_subtitle_and_chapter_payloads_are_deterministic():
    packet = SubtitlePacket(100, 220, "Grüße", "de", "text")
    encoded = encode_subtitle_packet(packet)
    assert decode_subtitle_packet(encoded) == packet
    chapters = [{"start_pts": 0, "end_pts": 1000, "title": "Intro", "language": "de"}]
    chapter_payload = encode_chapter_table(chapters)
    assert decode_chapter_table(chapter_payload) == chapters
    assert encode_chapter_table(chapters) == encode_chapter_table(list(reversed(chapters)))


def test_native_v2_text_payloads_fail_closed():
    with pytest.raises(ValueError):
        encode_subtitle_packet(SubtitlePacket(2, 1, "bad"))
    with pytest.raises(ValueError):
        decode_subtitle_packet(b"{}")
    with pytest.raises(ValueError):
        encode_chapter_table([{"start_pts": 2, "end_pts": 1, "title": "bad"}])
