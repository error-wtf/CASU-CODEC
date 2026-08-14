# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
import json
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest

from casu.core import analyze, sha256_file
from casu.export import CasuExportError, _burn_bitmap_subtitles, export_casu
from casu.native import write_native
from casu.native_v2 import (
    ChunkType, NativeChunk, convert_media_to_native_v2,
    decode_bitmap_subtitle, encode_bitmap_subtitle, encode_key_state,
    write_native_v2,
)
from casu.strict import canonical_frame


def _wav(path: Path, *, seconds: float = 0.1) -> Path:
    frames = int(8000 * seconds)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\0\0" * frames)
    return path


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg unavailable")
def test_export_sidecar_to_audio_format(tmp_path):
    source = _wav(tmp_path / "source.wav")
    manifest = tmp_path / "source.casu"
    manifest.write_text(json.dumps({
        "source": {"path": str(source), "filename": source.name,
                   "size_bytes": source.stat().st_size,
                   "sha256": sha256_file(source)},
    }), encoding="utf-8")
    output = export_casu(manifest, tmp_path / "output.flac")
    assert output.read_bytes().startswith(b"fLaC")


@pytest.mark.media
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg unavailable")
def test_export_sidecar_maps_all_av_text_tracks_and_chapters(tmp_path):
    subtitle = tmp_path / "caption.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:00,350\nMapped\n",
                        encoding="utf-8")
    metadata = tmp_path / "chapters.ffmeta"
    metadata.write_text(
        ";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=400\n"
        "title=Mapped chapter\n", encoding="utf-8")
    source = tmp_path / "multi.mkv"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
        "testsrc2=size=64x48:rate=5:duration=0.4", "-f", "lavfi", "-i",
        "sine=frequency=440:sample_rate=8000:duration=0.4", "-f", "lavfi", "-i",
        "sine=frequency=880:sample_rate=8000:duration=0.4", "-i", str(subtitle),
        "-i", str(metadata), "-map", "0:v:0", "-map", "1:a:0", "-map", "2:a:0",
        "-map", "3:s:0", "-map_chapters", "4", "-c:v", "ffv1", "-c:a",
        "pcm_s16le", "-c:s", "srt", "-y", str(source),
    ], check=True)
    sidecar = tmp_path / "multi.casu"
    sidecar.write_text(json.dumps({"source": {
        "path": str(source), "filename": source.name,
        "size_bytes": source.stat().st_size, "sha256": sha256_file(source),
    }}), encoding="utf-8")
    output = export_casu(sidecar, tmp_path / "mapped.mkv")
    probe = json.loads(subprocess.run([
        "ffprobe", "-v", "error", "-show_streams", "-show_chapters",
        "-of", "json", str(output),
    ], check=True, text=True, stdout=subprocess.PIPE).stdout)
    types = [item["codec_type"] for item in probe["streams"]]
    assert types.count("video") == 1
    assert types.count("audio") == 2
    assert types.count("subtitle") == 1
    assert probe["chapters"][0]["tags"]["title"] == "Mapped chapter"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg unavailable")
def test_export_casunat1_verifies_and_transcodes_payload(tmp_path):
    source = _wav(tmp_path / "source.wav")
    native = write_native(tmp_path / "source.casu", source, analyze(source))
    output = export_casu(native, tmp_path / "output.mp3")
    assert output.stat().st_size > 100


def test_export_rejects_non_casu_input(tmp_path):
    source = tmp_path / "source.mp3"
    source.write_bytes(b"not media")
    with pytest.raises(CasuExportError, match="CASU export failed"):
        export_casu(source, tmp_path / "output.wav")


@pytest.mark.media
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg unavailable")
def test_export_casunat2_video_and_audio_after_source_deletion(tmp_path):
    source = tmp_path / "source.mkv"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
        "testsrc2=size=64x48:rate=5:duration=0.4", "-f", "lavfi", "-i",
        "sine=frequency=440:sample_rate=8000:duration=0.4", "-c:v", "ffv1",
        "-c:a", "pcm_s16le", "-y", str(source),
    ], check=True)
    native = convert_media_to_native_v2(source, tmp_path / "source.casu",
                                        tile_width=16, tile_height=16)
    source.unlink()
    output = export_casu(native, tmp_path / "output.mp4")
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
        "-of", "csv=p=0", str(output),
    ], check=True, text=True, stdout=subprocess.PIPE).stdout.splitlines()
    assert "video" in probe
    assert "audio" in probe


def test_bitmap_subtitle_alpha_composite_and_timing():
    packet = decode_bitmap_subtitle(encode_bitmap_subtitle(
        start_pts=100, end_pts=300, canvas_width=4, canvas_height=4,
        x=1, y=1, width=2, height=2,
        rgba=bytes((255, 0, 0, 128)) * 4))
    black = np.zeros((8, 8, 3), dtype=np.uint8)
    before = _burn_bitmap_subtitles(black, 0.05, [packet])
    active = _burn_bitmap_subtitles(black, 0.2, [packet])
    after = _burn_bitmap_subtitles(black, 0.3, [packet])
    assert not before.any() and not after.any()
    assert np.all(active[2:6, 2:6, 0] == 128)
    assert not active[2:6, 2:6, 1:].any()


@pytest.mark.media
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg unavailable")
def test_export_casunat2_burns_default_bitmap_subtitle_without_source(tmp_path):
    black = canonical_frame(np.zeros((16, 48), dtype=np.uint8),
                            pixel_format="rgb24", source_shape=(16, 16))
    bitmap = encode_bitmap_subtitle(
        start_pts=0, end_pts=400, canvas_width=16, canvas_height=16,
        x=4, y=4, width=8, height=8,
        rgba=bytes((255, 0, 0, 255)) * 64)
    native = tmp_path / "bitmap.casu"
    write_native_v2(native, {
        "format": "CASUNAT2", "version": 2,
        "streams": [
            {"stream_id": 1, "type": "video", "codec_origin": "test",
             "time_base": [1, 1000], "frame_timeline": [
                 {"pts": 0, "duration_pts": 500},
                 {"pts": 500, "duration_pts": 500}]},
            {"stream_id": 2, "type": "subtitle",
             "codec_origin": "hdmv_pgs_subtitle", "default": True,
             "canonical_format": "rgba-bitmap-region",
             "time_base": [1, 1000]},
        ],
    }, [
        NativeChunk(ChunkType.VIDEO_KEY_STATE, 1, 0, encode_key_state(black)),
        NativeChunk(ChunkType.VIDEO_KEY_STATE, 1, 500, encode_key_state(black)),
        NativeChunk(ChunkType.SUBTITLE_BITMAP, 2, 0, bitmap),
    ])
    output = export_casu(native, tmp_path / "bitmap.mp4")
    raw = subprocess.run([
        "ffmpeg", "-v", "error", "-i", str(output), "-vf", "fps=2",
        "-frames:v", "2", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
    ], check=True, stdout=subprocess.PIPE).stdout
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 16, 16, 3)
    assert len(frames) == 2
    assert frames[0, 4:12, 4:12, 0].mean() > 180
    assert frames[0, 4:12, 4:12, 1:].mean() < 50
    assert frames[1, 4:12, 4:12].mean() < 50


@pytest.mark.media
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg unavailable")
def test_export_casunat2_preserves_multiple_native_av_streams(tmp_path):
    source = tmp_path / "multi.mkv"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
        "testsrc2=size=64x48:rate=5:duration=0.4", "-f", "lavfi", "-i",
        "sine=frequency=440:sample_rate=8000:duration=0.4", "-f", "lavfi", "-i",
        "sine=frequency=880:sample_rate=8000:duration=0.4",
        "-map", "0:v:0", "-map", "1:a:0", "-map", "2:a:0",
        "-c:v", "ffv1", "-c:a", "pcm_s16le", "-y", str(source),
    ], check=True)
    native = convert_media_to_native_v2(source, tmp_path / "multi.casu",
                                        tile_width=16, tile_height=16)
    output = export_casu(native, tmp_path / "restored.mkv")
    types = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
        "-of", "csv=p=0", str(output),
    ], check=True, text=True, stdout=subprocess.PIPE).stdout.splitlines()
    assert types.count("video") == 1
    assert types.count("audio") == 2


@pytest.mark.media
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg unavailable")
def test_export_casunat2_restores_text_subtitle_track(tmp_path):
    subtitle = tmp_path / "captions.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:00,350\nCASU subtitle\n",
                        encoding="utf-8")
    source = tmp_path / "subtitle.mkv"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
        "testsrc2=size=64x48:rate=5:duration=0.4", "-f", "lavfi", "-i",
        "sine=frequency=440:sample_rate=8000:duration=0.4", "-i", str(subtitle),
        "-map", "0:v:0", "-map", "1:a:0", "-map", "2:s:0",
        "-c:v", "ffv1", "-c:a", "pcm_s16le", "-c:s", "srt",
        "-y", str(source),
    ], check=True)
    native = convert_media_to_native_v2(source, tmp_path / "subtitle.casu",
                                        tile_width=16, tile_height=16)
    output = export_casu(native, tmp_path / "restored.mkv")
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
        "-of", "csv=p=0", str(output),
    ], check=True, text=True, stdout=subprocess.PIPE).stdout.splitlines()
    assert probe.count("subtitle") == 1


@pytest.mark.media
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg unavailable")
def test_export_casunat2_restores_rich_ass_source(tmp_path):
    subtitle = tmp_path / "styled.ass"
    subtitle.write_text(
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 64\nPlayResY: 48\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, "
        "SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
        "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: CASU,DejaVu Sans,12,&H00FFFFFF,&H000000FF,&H00000000,"
        "&H00000000,-1,0,0,0,100,100,0,0,1,1,0,2,4,4,4,1\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:00.35,CASU,,0,0,0,,{\\i1}Styled CASU\n",
        encoding="utf-8")
    source = tmp_path / "styled.mkv"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
        "testsrc2=size=64x48:rate=5:duration=0.4", "-i", str(subtitle),
        "-map", "0:v:0", "-map", "1:s:0", "-c:v", "ffv1", "-c:s", "ass",
        "-y", str(source),
    ], check=True)
    native = convert_media_to_native_v2(source, tmp_path / "styled.casu",
                                        tile_width=16, tile_height=16)
    output = export_casu(native, tmp_path / "restored.mkv")
    restored = subprocess.run([
        "ffmpeg", "-v", "error", "-i", str(output), "-map", "0:s:0",
        "-c:s", "copy", "-f", "ass", "pipe:1",
    ], check=True, stdout=subprocess.PIPE).stdout
    assert b"Style: CASU" in restored
    assert b"Styled CASU" in restored


@pytest.mark.media
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg unavailable")
def test_export_casunat2_restores_chapters(tmp_path):
    metadata = tmp_path / "chapters.ffmeta"
    metadata.write_text(
        ";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=200\n"
        "title=Intro\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=200\nEND=400\n"
        "title=Finale\n", encoding="utf-8")
    source = tmp_path / "chapters.mkv"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
        "sine=frequency=440:sample_rate=8000:duration=0.4",
        "-i", str(metadata), "-map", "0:a:0", "-map_metadata", "1",
        "-map_chapters", "1", "-c:a", "pcm_s16le", "-y", str(source),
    ], check=True)
    native = convert_media_to_native_v2(source, tmp_path / "chapters.casu")
    output = export_casu(native, tmp_path / "restored.mka")
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-show_chapters", "-of", "json", str(output),
    ], check=True, text=True, stdout=subprocess.PIPE)
    chapters = json.loads(probe.stdout)["chapters"]
    assert [item["tags"]["title"] for item in chapters] == ["Intro", "Finale"]
    assert float(chapters[1]["start_time"]) == pytest.approx(0.2, abs=0.001)
