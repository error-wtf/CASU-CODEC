from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from casu.core import analyze
from casu.strict import (StrictCanonicalError, StrictFrame, build_state_map,
                         canonical_frame, iter_source_frames, validate_source_frames)


def _yuv420(depth: int = 8):
    dtype = np.uint8 if depth == 8 else np.uint16
    return (np.zeros((4, 4), dtype=dtype), np.zeros((2, 2), dtype=dtype),
            np.zeros((2, 2), dtype=dtype))


def test_native_strict_identical_rgb24_holds_and_single_sample_updates():
    first = np.zeros((3, 12), dtype=np.uint8)
    second = first.copy()
    frame_a = canonical_frame(first, pixel_format="rgb24", source_shape=(3, 4))
    held = build_state_map([StrictFrame(0, 1, 1000, frame_a),
                            StrictFrame(41, 1, 1000, frame_a)], tile_width=2, tile_height=2)
    assert any(item["state"] == "HOLD" for item in held)
    second[0, 0] = 1
    frame_b = canonical_frame(second, pixel_format="rgb24", source_shape=(3, 4))
    changed = build_state_map([StrictFrame(0, 1, 1000, frame_a),
                               StrictFrame(41, 1, 1000, frame_b)], tile_width=2, tile_height=2)
    assert any(item["state"] == "UPDATE" for item in changed)


def test_native_strict_chroma_single_sample_updates():
    planes = _yuv420()
    changed = tuple(plane.copy() for plane in planes)
    changed[1][0, 0] = 1
    before = canonical_frame(planes, pixel_format="yuv420p", source_shape=(4, 4))
    after = canonical_frame(changed, pixel_format="yuv420p", source_shape=(4, 4))
    states = build_state_map([StrictFrame(0, 1, 1000, before),
                              StrictFrame(41, 1, 1000, after)], tile_width=4, tile_height=4)
    assert states[-1]["state"] == "UPDATE"


def test_native_strict_alpha_single_sample_updates():
    y, u, v = _yuv420()
    alpha = np.zeros((4, 4), dtype=np.uint8)
    before = canonical_frame((y, u, v, alpha), pixel_format="yuva420p", source_shape=(4, 4))
    changed = alpha.copy(); changed[3, 3] = 1
    after = canonical_frame((y, u, v, changed), pixel_format="yuva420p", source_shape=(4, 4))
    states = build_state_map([StrictFrame(0, 1, 1000, before),
                              StrictFrame(41, 1, 1000, after)], tile_width=4, tile_height=4)
    assert states[-1]["state"] == "UPDATE"


def _assert_high_bit_depth_update(depth):
    planes = _yuv420(depth)
    changed = tuple(plane.copy() for plane in planes)
    changed[0][2, 2] = 1
    fmt = f"yuv420p{depth}le"
    before = canonical_frame(planes, pixel_format=fmt, source_shape=(4, 4))
    after = canonical_frame(changed, pixel_format=fmt, source_shape=(4, 4))
    states = build_state_map([StrictFrame(0, 1, 90000, before),
                              StrictFrame(3600, 1, 90000, after)], tile_width=4, tile_height=4)
    assert states[-1]["state"] == "UPDATE"
    assert before.plane_layouts[0].bit_depth == depth


def test_native_strict_10bit_single_sample_updates():
    _assert_high_bit_depth_update(10)


@pytest.mark.parametrize("depth", [12, 16])
def test_native_strict_other_high_bit_depth_single_sample_updates(depth):
    _assert_high_bit_depth_update(depth)


def test_native_strict_format_metadata_and_resolution_changes_force_key_state():
    planes = _yuv420()
    first = canonical_frame(planes, pixel_format="yuv420p", source_shape=(4, 4),
                            color_metadata={"color_space": "bt709"})
    color_change = canonical_frame(planes, pixel_format="yuv420p", source_shape=(4, 4),
                                   color_metadata={"color_space": "bt2020nc"})
    larger = canonical_frame((np.zeros((6, 6), dtype=np.uint8),
                              np.zeros((3, 3), dtype=np.uint8),
                              np.zeros((3, 3), dtype=np.uint8)),
                             pixel_format="yuv420p", source_shape=(6, 6))
    states = build_state_map([StrictFrame(0, 1, 1000, first),
                              StrictFrame(40, 1, 1000, color_change),
                              StrictFrame(80, 1, 1000, larger)], tile_width=8, tile_height=8)
    assert [item["state"] for item in states] == ["KEY_STATE", "KEY_STATE", "KEY_STATE"]
    assert states[1]["format_change"] is True


def test_native_strict_preserves_vfr_pts():
    frame = canonical_frame(np.zeros((2, 2), dtype=np.uint8), pixel_format="gray8")
    source = [StrictFrame(0, 1, 1000, frame), StrictFrame(41, 1, 1000, frame),
              StrictFrame(83, 1, 1000, frame), StrictFrame(200, 1, 1000, frame)]
    states = build_state_map(source, tile_width=2, tile_height=2)
    assert [item["valid_from"]["pts"] for item in states] == [0, 41, 83, 200]
    assert [item["valid_from_s"] for item in states] == [0.0, 0.041, 0.083, 0.2]


def test_native_strict_rejects_nonpresentation_order_pts():
    frame = canonical_frame(np.zeros((2, 2), dtype=np.uint8), pixel_format="gray8")
    with pytest.raises(ValueError, match="presentation order"):
        validate_source_frames([StrictFrame(2, 1, 1000, frame),
                                StrictFrame(1, 1, 1000, frame)])


def test_native_strict_unsupported_canonicalization_fails_closed():
    with pytest.raises(StrictCanonicalError, match="unsupported"):
        canonical_frame(np.zeros((2, 2), dtype=np.uint8), pixel_format="pal8")
    with pytest.raises(StrictCanonicalError, match="requires 3 planes"):
        canonical_frame(np.zeros((2, 2), dtype=np.uint8), pixel_format="yuv420p")
    bad = _yuv420(10)
    bad[0][0, 0] = 1024
    with pytest.raises(StrictCanonicalError, match="outside 10-bit"):
        canonical_frame(bad, pixel_format="yuv420p10le", source_shape=(4, 4))


def test_production_strict_path_uses_source_decoder_not_preview(tmp_path, monkeypatch):
    source = tmp_path / "source.fake"
    source.write_bytes(b"fixture")
    frame = canonical_frame(np.zeros((2, 2), dtype=np.uint8), pixel_format="gray8")
    monkeypatch.setattr("casu.core.ffprobe", lambda _path: {
        "streams": [{"index": 0, "codec_type": "video", "codec_name": "raw",
                     "width": 2, "height": 2, "pix_fmt": "gray8", "time_base": "1/1000",
                     "nb_frames": "2"}],
        "format": {"duration": "0.080", "format_name": "fixture"},
    })
    monkeypatch.setattr("casu.core.iter_source_frames", lambda _path, **_kwargs: iter([
        StrictFrame(0, 1, 1000, frame, 40), StrictFrame(40, 1, 1000, frame, 40)]))
    monkeypatch.setattr("casu.core.preview_activity_analysis",
                        lambda *_args, **_kwargs: pytest.fail("preview path used for STRICT"))
    manifest = analyze(source, mode="strict")
    spatial = manifest["video"]["spatial_analysis"]
    assert spatial["strict_pixel_identical_available"] is True
    assert spatial["state_counts"] == {"KEY_STATE": 1, "UPDATE": 0, "HOLD": 1}
    assert manifest["video"]["state_is_hint_only"] is False


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


@pytest.mark.media
@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="ffmpeg/ffprobe unavailable")
def test_native_strict_real_vfr_pts_match_ffprobe(tmp_path):
    source = tmp_path / "vfr.mkv"
    _run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
          "-i", "testsrc2=size=16x16:rate=25:duration=0.28",
          "-vf", "select=eq(n\\,0)+eq(n\\,1)+eq(n\\,2)+eq(n\\,5)",
          "-fps_mode", "vfr", "-c:v", "ffv1", "-pix_fmt", "yuv420p", str(source)])
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_frames", "-of", "json", str(source)], check=True,
                           stdout=subprocess.PIPE)
    expected = [int(item["best_effort_timestamp"]) for item in
                json.loads(probe.stdout)["frames"]]
    decoded = list(iter_source_frames(source))
    assert [item.pts for item in decoded] == expected
    assert len(set(b - a for a, b in zip(expected, expected[1:]))) > 1


@pytest.mark.media
@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="ffmpeg/ffprobe unavailable")
def test_native_strict_decoder_can_be_closed_without_broken_pipe_error(tmp_path):
    source = tmp_path / "close.mkv"
    _run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
          "testsrc2=size=16x16:rate=25:duration=1", "-c:v", "ffv1", str(source)])
    decoded = iter_source_frames(source, engine="ffmpeg")
    assert next(decoded).frame.shape == (16, 16)
    decoded.close()


@pytest.mark.media
@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="ffmpeg/ffprobe unavailable")
def test_native_strict_b_frames_arrive_in_presentation_order(tmp_path):
    source = tmp_path / "bframes.mkv"
    _run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
          "-i", "testsrc2=size=32x24:rate=25:duration=0.4", "-c:v", "mpeg4",
          "-bf", "2", "-q:v", "2", "-pix_fmt", "yuv420p", str(source)])
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_frames", "-of", "json", str(source)], check=True,
                           stdout=subprocess.PIPE)
    inventory = json.loads(probe.stdout)["frames"]
    assert any(item.get("pict_type") == "B" for item in inventory)
    expected = [int(item["best_effort_timestamp"]) for item in inventory]
    decoded = list(iter_source_frames(source))
    assert [item.pts for item in decoded] == expected
    assert expected == sorted(expected)


@pytest.mark.media
@pytest.mark.parametrize("pixel_format,expected_shapes", [
    ("yuv422p", [(16, 24), (16, 12), (16, 12)]),
    ("yuv444p", [(16, 24), (16, 24), (16, 24)]),
    ("yuv420p10le", [(16, 24), (8, 12), (8, 12)]),
    ("yuv420p12le", [(16, 24), (8, 12), (8, 12)]),
    ("yuv420p16le", [(16, 24), (8, 12), (8, 12)]),
    ("yuva420p", [(16, 24), (8, 12), (8, 12), (16, 24)]),
])
@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="ffmpeg/ffprobe unavailable")
def test_native_strict_real_source_formats(tmp_path, pixel_format, expected_shapes):
    source = tmp_path / f"{pixel_format}.mkv"
    try:
        _run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
              "-i", "testsrc2=size=24x16:rate=2:duration=1", "-c:v", "ffv1",
              "-pix_fmt", pixel_format, str(source)])
    except subprocess.CalledProcessError:
        pytest.skip(f"local FFmpeg cannot encode {pixel_format}")
    frames = list(iter_source_frames(source, max_frames=1))
    assert len(frames) == 1
    assert frames[0].frame.pixel_format == pixel_format
    assert [tuple(plane.shape) for plane in frames[0].frame.planes] == expected_shapes
    assert all(plane.flags.c_contiguous and not plane.flags.writeable
               for plane in frames[0].frame.planes)


@pytest.mark.media
@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="ffmpeg/ffprobe unavailable")
def test_production_analyze_real_media_emits_strict_source_state_map(tmp_path):
    source = tmp_path / "strict.mkv"
    _run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
          "-i", "testsrc2=size=24x16:rate=3:duration=1", "-c:v", "ffv1",
          "-pix_fmt", "yuv420p", str(source)])
    manifest = analyze(source, mode="strict")
    spatial = manifest["video"]["spatial_analysis"]
    assert spatial["strict_pixel_identical_available"] is True
    assert spatial["state_map_coordinate_system"] == "source-display-pixels"
    assert {item["valid_from"]["time_base_den"] for item in spatial["state_map"]} == {1000}
    assert spatial["state_counts"]["KEY_STATE"] > 0
