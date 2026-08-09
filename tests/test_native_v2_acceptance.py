from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from casu.native_v2 import (ChunkType, convert_media_to_native_v2,
                            decode_audio_block, decode_chapter_table,
                            decode_subtitle_packet, decode_attachment,
                            decode_bitmap_subtitle,
                            read_native_v2)
from casu.strict import iter_source_frames


pytestmark = [
    pytest.mark.media,
    pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                       reason="ffmpeg/ffprobe unavailable"),
]

PGS_SAMPLE = Path(os.environ.get("CASU_TEST_PGS", "")) if os.environ.get("CASU_TEST_PGS") else None


def _fixture(path):
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", "testsrc2=size=32x24:rate=5:duration=1",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=8000:duration=1",
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "ffv1", "-pix_fmt", "yuv420p",
        "-c:a", "pcm_s16le", "-shortest", str(path),
    ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _pcm(source):
    return subprocess.run(["ffmpeg", "-v", "error", "-i", str(source), "-map", "0:a:0",
                           "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le",
                           "-acodec", "pcm_s16le", "pipe:1"], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def test_casunat2_contains_video_key_state(tmp_path):
    source = tmp_path / "source.mkv"; _fixture(source)
    target = convert_media_to_native_v2(source, tmp_path / "output.casu")
    container = read_native_v2(target)
    kinds = [chunk.chunk_type for chunk in container.chunks]
    assert ChunkType.VIDEO_KEY_STATE in kinds
    assert ChunkType.VIDEO_TILE_UPDATE in kinds
    assert ChunkType.AUDIO_BLOCK in kinds
    assert container.manifest["format"] == "CASUNAT2"
    assert "path" not in container.manifest["source_provenance"]


def test_casunat2_seek_index_uses_valid_byte_offsets(tmp_path):
    source = tmp_path / "source.mkv"; _fixture(source)
    target = convert_media_to_native_v2(source, tmp_path / "output.casu",
                                        max_key_interval_seconds=0.25)
    container = read_native_v2(target)
    video_stream = next(item["stream_id"] for item in container.manifest["streams"]
                        if item["type"] == "video")
    assert len(container.seek_entries) >= 2
    for entry in container.seek_entries:
        chunk, _ = container.read_chunk_at(entry.key_state_offset)
        assert chunk.chunk_type == ChunkType.VIDEO_KEY_STATE
        assert chunk.stream_id == entry.stream_id
        assert chunk.pts == entry.key_state_pts
    plan = container.seek_video(video_stream, 600)
    assert plan.key_state_pts <= 600
    assert plan.key_state_offset > 0


def test_casunat2_survives_source_deletion(tmp_path):
    source = tmp_path / "source.mkv"; _fixture(source)
    expected_frames = list(iter_source_frames(source))
    expected = {frame.pts: frame.frame.digest() for frame in expected_frames}
    target = convert_media_to_native_v2(source, tmp_path / "output.casu")
    source.unlink()
    container = read_native_v2(target)
    video_stream = next(item["stream_id"] for item in container.manifest["streams"]
                        if item["type"] == "video")
    for pts, digest in expected.items():
        assert container.reconstruct_video(video_stream, pts).digest() == digest


def test_casunat2_audio_blocks_roundtrip_canonical_pcm_after_source_deletion(tmp_path):
    source = tmp_path / "source.mkv"; _fixture(source)
    expected_pcm = _pcm(source)
    target = convert_media_to_native_v2(source, tmp_path / "output.casu")
    source.unlink()
    container = read_native_v2(target)
    audio_stream = next(item["stream_id"] for item in container.manifest["streams"]
                        if item["type"] == "audio")
    blocks = [decode_audio_block(chunk.payload) for chunk in container.chunks
              if chunk.chunk_type == ChunkType.AUDIO_BLOCK and chunk.stream_id == audio_stream]
    actual_pcm = b"".join(block.pcm for block in blocks)
    assert hashlib.sha256(actual_pcm).digest() == hashlib.sha256(expected_pcm).digest()
    assert blocks and all(block.sample_rate == 8000 and block.channels == 1 for block in blocks)
    assert [block.pts for block in blocks] == sorted(block.pts for block in blocks)


def test_casunat2_converts_text_subtitles_and_chapters(tmp_path):
    subtitle = tmp_path / "captions.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:00,800\nHallo CASU\n", encoding="utf-8")
    metadata = tmp_path / "chapters.ffmeta"
    metadata.write_text(
        ";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=800\ntitle=Intro\n",
        encoding="utf-8")
    source = tmp_path / "text.mkv"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", "testsrc2=size=16x16:rate=2:duration=1",
        "-f", "lavfi", "-i", "sine=sample_rate=8000:duration=1",
        "-i", str(subtitle), "-i", str(metadata),
        "-map", "0:v:0", "-map", "1:a:0", "-map", "2:s:0", "-map_metadata", "3",
        "-c:v", "ffv1", "-c:a", "pcm_s16le", "-c:s", "srt", "-shortest", str(source),
    ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    target = convert_media_to_native_v2(source, tmp_path / "text.casu")
    source.unlink(); subtitle.unlink(); metadata.unlink()
    container = read_native_v2(target)
    subtitle_packets = [decode_subtitle_packet(chunk.payload) for chunk in container.chunks
                        if chunk.chunk_type == ChunkType.SUBTITLE_PACKET]
    chapter_tables = [decode_chapter_table(chunk.payload) for chunk in container.chunks
                      if chunk.chunk_type == ChunkType.CHAPTER_TABLE]
    assert subtitle_packets[0].text == "Hallo CASU"
    assert subtitle_packets[0].language == "und"
    assert chapter_tables[0][0]["title"] == "Intro"


def test_casunat2_preserves_ass_styles_with_playable_text_fallback(tmp_path):
    subtitle = tmp_path / "styled.ass"
    subtitle.write_text(
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 320\nPlayResY: 180\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: CASU,DejaVu Sans,24,&H00FFFFFF,&H000000FF,&H00000000," 
        "&H00000000,-1,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:00.80,CASU,,0,0,0,,{\\i1}Styled CASU{\\i0}\n",
        encoding="utf-8",
    )
    source = tmp_path / "styled.mkv"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
        "testsrc2=size=32x24:rate=2:duration=1", "-i", str(subtitle),
        "-map", "0:v:0", "-map", "1:s:0", "-c:v", "ffv1", "-c:s", "ass",
        str(source),
    ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    target = convert_media_to_native_v2(source, tmp_path / "styled.casu")
    source.unlink(); subtitle.unlink()
    container = read_native_v2(target)
    descriptor = next(stream for stream in container.manifest["streams"]
                      if stream["type"] == "subtitle")
    assert descriptor["rich_source_attachment"] is True
    attachments = [decode_attachment(chunk.payload) for chunk in container.chunks
                   if chunk.chunk_type == ChunkType.ATTACHMENT]
    rich = next(item for item in attachments if item.role == "subtitle-source")
    assert b"Style: CASU" in rich.data and b"Dialogue:" in rich.data
    fallback = [decode_subtitle_packet(chunk.payload) for chunk in container.chunks
                if chunk.chunk_type == ChunkType.SUBTITLE_PACKET]
    assert fallback and "Styled CASU" in fallback[0].text


@pytest.mark.skipif(PGS_SAMPLE is None or not PGS_SAMPLE.is_file(),
                    reason="set CASU_TEST_PGS to an authorized PGS sample")
def test_casunat2_decodes_real_pgs_bitmap_after_source_deletion(tmp_path):
    source = tmp_path / "pgs.mkv"
    shutil.copy2(PGS_SAMPLE, source)
    target = convert_media_to_native_v2(source, tmp_path / "pgs.casu")
    source.unlink()
    container = read_native_v2(target)
    descriptor = next(stream for stream in container.manifest["streams"]
                      if stream.get("codec_origin") == "hdmv_pgs_subtitle")
    assert descriptor["canonical_format"] == "rgba-bitmap-region"
    packets = [decode_bitmap_subtitle(chunk.payload) for chunk in container.chunks
               if chunk.chunk_type == ChunkType.SUBTITLE_BITMAP]
    assert packets and all(packet.end_pts > packet.start_pts for packet in packets)
    assert all(packet.canvas_rgba().shape ==
               (packet.canvas_height, packet.canvas_width, 4) for packet in packets)


def test_casunat2_preserves_source_attachments(tmp_path):
    attachment = tmp_path / "note.txt"; attachment.write_bytes(b"standalone CASU attachment")
    source = tmp_path / "attachment.mkv"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
        "testsrc2=size=16x16:rate=1:duration=1", "-attach", str(attachment),
        "-metadata:s:t:0", "mimetype=text/plain", "-metadata:s:t:0", "filename=note.txt",
        "-c:v", "ffv1", str(source),
    ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    target = convert_media_to_native_v2(source, tmp_path / "attachment.casu")
    source.unlink(); attachment.unlink()
    container = read_native_v2(target)
    attachments = [decode_attachment(chunk.payload) for chunk in container.chunks
                   if chunk.chunk_type == ChunkType.ATTACHMENT]
    assert len(attachments) == 1
    assert attachments[0].filename == "note.txt"
    assert attachments[0].data == b"standalone CASU attachment"


def test_casunat2_labels_embedded_subtitle_fonts(tmp_path):
    font = tmp_path / "CASU.ttf"; font.write_bytes(b"bounded fake font payload")
    source = tmp_path / "font.mkv"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
        "testsrc2=size=16x16:rate=1:duration=1", "-attach", str(font),
        "-metadata:s:t:0", "mimetype=font/ttf", "-metadata:s:t:0", "filename=CASU.ttf",
        "-c:v", "ffv1", str(source),
    ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    target = convert_media_to_native_v2(source, tmp_path / "font.casu")
    container = read_native_v2(target)
    attachment = next(decode_attachment(chunk.payload) for chunk in container.chunks
                      if chunk.chunk_type == ChunkType.ATTACHMENT)
    assert attachment.role == "subtitle-font"
    assert attachment.filename == "CASU.ttf"


def test_casunat2_preserves_attached_cover_as_attachment_not_video(tmp_path):
    cover = tmp_path / "cover.png"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
        "color=c=blue:size=24x16", "-frames:v", "1", str(cover),
    ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    source = tmp_path / "album.mp3"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
        "sine=frequency=440:sample_rate=8000:duration=0.25", "-i", str(cover),
        "-map", "0:a:0", "-map", "1:v:0", "-c:a", "libmp3lame", "-c:v", "png",
        "-disposition:v:0", "attached_pic", "-metadata:s:v:0", "title=Front Cover",
        "-metadata", "title=CASU Album", "-metadata", "artist=Lino",
        str(source),
    ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    target = convert_media_to_native_v2(source, tmp_path / "album.casu")
    source.unlink(); cover.unlink()
    container = read_native_v2(target)
    assert not [stream for stream in container.manifest["streams"]
                if stream["type"] == "video"]
    cover_stream = next(stream for stream in container.manifest["streams"]
                        if stream.get("role") == "cover-art")
    payload = next(chunk.payload for chunk in container.chunks
                   if chunk.chunk_type == ChunkType.ATTACHMENT
                   and chunk.stream_id == cover_stream["stream_id"])
    attachment = decode_attachment(payload)
    assert attachment.role == "cover-art"
    assert attachment.media_type == "image/png"
    assert attachment.data.startswith(b"\x89PNG\r\n\x1a\n")
    assert container.manifest["metadata"]["title"] == "CASU Album"
    assert container.manifest["metadata"]["artist"] == "Lino"
    assert cover_stream["disposition"]["attached_pic"] is True
    assert cover_stream["tags"]["title"] == "Front Cover"
