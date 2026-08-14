from __future__ import annotations

import hashlib
import json
from fractions import Fraction

import numpy as np
import pytest

from casu.native_v2 import (CasuLimits, ChunkType, NativeChunk, NativeV2Error,
                            SubtitlePacket, encode_audio_block,
                            encode_chapter_table, encode_format_change,
                            encode_key_state, encode_tile_update,
                            encode_subtitle_packet, read_native_v2,
                            recover_native_v2, write_native_v2)
from casu.native_v2.format import SeekEntry
from casu.native_v2.validation import NativeV2ValidationError
from casu.native_v2.converter import _video_chunks
from casu.native_v2.writer import (CHUNK_HEADER, HEADER, MAGIC, VERSION,
                                   _pack_chunk)
from casu.strict import StrictFrame, canonical_frame


def _video_descriptor(stream_id: int = 1) -> dict:
    return {"stream_id": stream_id, "type": "video", "time_base": [1, 1000],
            "width": 2, "height": 2, "pix_fmt": "rgb24"}


def _audio_descriptor(stream_id: int = 1) -> dict:
    return {"stream_id": stream_id, "type": "audio", "time_base": [1, 1000],
            "sample_rate": 1000, "channels": 1}


def _manifest(*streams: dict) -> dict:
    return {"format": "CASUNAT2", "version": 2,
            "streams": list(streams)}


def _key_payload() -> bytes:
    return encode_key_state(canonical_frame(
        np.zeros((2, 6), dtype=np.uint8), pixel_format="rgb24",
        source_shape=(2, 2)))


def _coherent_untrusted_file(path, manifest: dict,
                             user_chunks: list[NativeChunk], *,
                             index_all_keys: bool = True,
                             omit_first_hash: bool = False) -> None:
    """Build a globally hash-consistent file without the production writer."""
    manifest_bytes = json.dumps(manifest, sort_keys=True,
                                separators=(",", ":")).encode()
    prefix = bytearray(HEADER.pack(MAGIC, VERSION, 0, len(manifest_bytes)))
    prefix.extend(manifest_bytes)
    hashes = []
    keys = []
    for chunk in user_chunks:
        offset = len(prefix)
        packed = _pack_chunk(chunk)
        prefix.extend(packed)
        hashes.append({"offset": offset,
                       "sha256": hashlib.sha256(packed).hexdigest()})
        if chunk.chunk_type == ChunkType.VIDEO_KEY_STATE and index_all_keys:
            keys.append(SeekEntry(chunk.stream_id, chunk.pts, chunk.pts,
                                  offset, offset))
    index_offset = len(prefix)
    index_payload = json.dumps(
        {"version": 1, "entries": [entry.__dict__ for entry in keys]},
        sort_keys=True, separators=(",", ":")).encode()
    index = _pack_chunk(NativeChunk(ChunkType.SEEK_INDEX, 0, 0,
                                    index_payload))
    prefix.extend(index)
    hashes.append({"offset": index_offset,
                   "sha256": hashlib.sha256(index).hexdigest()})
    if omit_first_hash:
        hashes = hashes[1:]
    integrity = _pack_chunk(NativeChunk(
        ChunkType.INTEGRITY_TABLE, 0, index_offset,
        json.dumps({"sha256_before_integrity": hashlib.sha256(prefix).hexdigest(),
                    "chunk_sha256": hashes}, sort_keys=True,
                   separators=(",", ":")).encode()))
    prefix.extend(integrity)
    prefix.extend(_pack_chunk(NativeChunk(ChunkType.END, 0, 0, b"")))
    path.write_bytes(prefix)


def test_writer_rejects_invalid_manifest_and_stream_identity(tmp_path):
    duplicate = _manifest(_video_descriptor(1), _audio_descriptor(1))
    with pytest.raises(NativeV2ValidationError, match="duplicated"):
        write_native_v2(tmp_path / "duplicate.casu", duplicate, [])
    unsafe = _manifest(_video_descriptor())
    unsafe["source_provenance"] = {"path": "/secret/input.mp4"}
    with pytest.raises(NativeV2ValidationError, match="must not contain a path"):
        write_native_v2(tmp_path / "path.casu", unsafe, [])


def test_reader_rejects_coherently_hashed_duplicate_stream_ids(tmp_path):
    target = tmp_path / "duplicate.casu"
    _coherent_untrusted_file(
        target, _manifest(_video_descriptor(1), _audio_descriptor(1)), [])
    with pytest.raises(NativeV2Error, match="duplicated"):
        read_native_v2(target)


def test_reader_rejects_chunk_stream_type_confusion(tmp_path):
    target = tmp_path / "confused.casu"
    audio = encode_audio_block(
        pcm=b"\0\0", pts=0, time_base_num=1, time_base_den=1000,
        sample_rate=1000, channels=1, sample_count=1)
    _coherent_untrusted_file(
        target, _manifest(_video_descriptor()),
        [NativeChunk(ChunkType.AUDIO_BLOCK, 1, 0, audio)])
    with pytest.raises(NativeV2Error, match="does not match"):
        read_native_v2(target)


def test_verify_rejects_semantically_invalid_payload_with_valid_hashes(tmp_path):
    target = tmp_path / "bad-payload.casu"
    _coherent_untrusted_file(
        target, _manifest(_video_descriptor()),
        [NativeChunk(ChunkType.VIDEO_KEY_STATE, 1, 0, b"not-a-frame")])
    with pytest.raises(NativeV2Error, match="video_key_state payload"):
        read_native_v2(target)
    # Lazy consumers validate topology/integrity first and still fail later at
    # their bounded payload decoder rather than allocating all media on open.
    assert read_native_v2(target, load_payloads=False).integrity_verified


def test_reader_requires_exact_per_chunk_hash_coverage(tmp_path):
    target = tmp_path / "missing-hash.casu"
    _coherent_untrusted_file(
        target, _manifest(_video_descriptor()),
        [NativeChunk(ChunkType.VIDEO_KEY_STATE, 1, 0, _key_payload())],
        omit_first_hash=True)
    with pytest.raises(NativeV2Error, match="hash table"):
        read_native_v2(target)


def test_reader_requires_seek_entry_for_every_key_state(tmp_path):
    target = tmp_path / "missing-index.casu"
    _coherent_untrusted_file(
        target, _manifest(_video_descriptor()),
        [NativeChunk(ChunkType.VIDEO_KEY_STATE, 1, 0, _key_payload())],
        index_all_keys=False)
    with pytest.raises(NativeV2Error, match="every video key state"):
        read_native_v2(target)


def test_unknown_chunk_flags_and_duplicate_chapters_fail_closed(tmp_path):
    flagged = tmp_path / "flags.casu"
    _coherent_untrusted_file(
        flagged, _manifest(_video_descriptor()),
        [NativeChunk(ChunkType.VIDEO_KEY_STATE, 1, 0, _key_payload(), flags=1)])
    with pytest.raises(NativeV2Error, match="unknown flags"):
        read_native_v2(flagged)
    chapter = encode_chapter_table([
        {"start_pts": 0, "end_pts": 1, "title": "One"}])
    duplicate = tmp_path / "chapters.casu"
    _coherent_untrusted_file(duplicate, _manifest(), [
        NativeChunk(ChunkType.CHAPTER_TABLE, 0, 0, chapter),
        NativeChunk(ChunkType.CHAPTER_TABLE, 0, 0, chapter),
    ])
    with pytest.raises(NativeV2Error, match="duplicate.*chapter"):
        read_native_v2(duplicate)


def test_payload_pts_and_stream_config_must_match_manifest(tmp_path):
    audio_descriptor = _audio_descriptor()
    mismatched_audio = encode_audio_block(
        pcm=b"\0\0", pts=1, time_base_num=1, time_base_den=1000,
        sample_rate=1000, channels=1, sample_count=1)
    with pytest.raises(NativeV2ValidationError, match="audio block differs"):
        write_native_v2(tmp_path / "pts.casu", _manifest(audio_descriptor), [
            NativeChunk(ChunkType.AUDIO_BLOCK, 1, 0, mismatched_audio)])
    with pytest.raises(NativeV2ValidationError, match="config differs"):
        write_native_v2(tmp_path / "config.casu", _manifest(audio_descriptor), [
            NativeChunk(ChunkType.STREAM_CONFIG, 1, 0, b"{}")])


def test_truncated_recovery_requires_valid_checkpoint(tmp_path):
    target = tmp_path / "recover.casu"
    write_native_v2(target, _manifest(_video_descriptor()), [
        NativeChunk(ChunkType.VIDEO_KEY_STATE, 1, 0, _key_payload())
    ], recovery_interval=1)
    container = read_native_v2(target)
    position = next(offset for offset, chunk in zip(container.offsets,
                                                    container.chunks)
                    if chunk.chunk_type == ChunkType.RECOVERY_POINT)
    raw = bytearray(target.read_bytes())
    payload_start = position + CHUNK_HEADER.size
    payload_end = payload_start + len(next(
        chunk.payload for chunk in container.chunks
        if chunk.chunk_type == ChunkType.RECOVERY_POINT))
    marker = raw.find(b'"checkpoint_sha256":"', payload_start, payload_end)
    assert marker >= 0
    digit = marker + len(b'"checkpoint_sha256":"')
    raw[digit] = ord("0") if raw[digit] != ord("0") else ord("1")
    target.write_bytes(raw[:payload_end])
    with pytest.raises(NativeV2Error, match="no usable recovery point"):
        recover_native_v2(target)


def test_subtitle_chunk_header_pts_must_match_payload(tmp_path):
    subtitle = {"stream_id": 1, "type": "subtitle",
                "time_base": [1, 1000]}
    payload = encode_subtitle_packet(SubtitlePacket(10, 20, "text"))
    with pytest.raises(NativeV2ValidationError, match="subtitle packet PTS"):
        write_native_v2(tmp_path / "subtitle.casu", _manifest(subtitle), [
            NativeChunk(ChunkType.SUBTITLE_PACKET, 1, 9, payload)])


def test_strict_json_rejects_duplicate_keys_and_nonfinite_writer_values(tmp_path):
    target = tmp_path / "duplicate-json.casu"
    descriptor = _audio_descriptor()
    duplicate_config = (
        b'{"channels":1,"sample_rate":1000,"stream_id":1,'
        b'"stream_id":1,"time_base":[1,1000],"type":"audio"}')
    _coherent_untrusted_file(target, _manifest(descriptor), [
        NativeChunk(ChunkType.STREAM_CONFIG, 1, 0, duplicate_config)])
    with pytest.raises(NativeV2Error, match="stream config"):
        read_native_v2(target)
    nonfinite = _manifest(descriptor)
    nonfinite["source_provenance"] = {"duration_s": float("nan")}
    with pytest.raises(ValueError, match="not finite"):
        write_native_v2(tmp_path / "nan.casu", nonfinite, [])


def test_writer_enforces_total_file_limit_and_removes_temporary(tmp_path):
    target = tmp_path / "limited.casu"
    with pytest.raises(ValueError, match="limit"):
        write_native_v2(
            target, _manifest(_video_descriptor()),
            [NativeChunk(ChunkType.VIDEO_KEY_STATE, 1, 0, _key_payload())],
            limits=CasuLimits(max_file_bytes=256))
    assert not target.exists()
    assert not list(tmp_path.glob(".limited.casu.*"))


def test_format_change_is_explicit_keyed_and_random_accessible(
        tmp_path, monkeypatch):
    first = canonical_frame(np.zeros((2, 6), dtype=np.uint8),
                            pixel_format="rgb24", source_shape=(2, 2))
    second = canonical_frame(np.full((3, 12), 7, dtype=np.uint8),
                             pixel_format="rgb24", source_shape=(3, 4))
    monkeypatch.setattr(
        "casu.native_v2.converter.iter_source_frames",
        lambda *_args, **_kwargs: iter((
            StrictFrame(0, 1, 1000, first),
            StrictFrame(10, 1, 1000, second),
        )))
    chunks = list(_video_chunks(tmp_path / "unused", 1, 0,
                                Fraction(3), 2, 2, None))
    assert [chunk.chunk_type for chunk in chunks] == [
        ChunkType.VIDEO_KEY_STATE, ChunkType.VIDEO_FORMAT_CHANGE,
        ChunkType.VIDEO_KEY_STATE]
    target = tmp_path / "format-change.casu"
    descriptor = _video_descriptor()
    descriptor["frame_timeline"] = [
        {"pts": 0, "duration_pts": 10},
        {"pts": 10, "duration_pts": 10}]
    write_native_v2(target, _manifest(descriptor), chunks)
    container = read_native_v2(target)
    assert container.reconstruct_video(1, 0).shape == (2, 2)
    assert container.reconstruct_video(1, 10).shape == (3, 4)


def test_format_change_without_immediate_key_is_rejected(tmp_path):
    first = canonical_frame(np.zeros((2, 6), dtype=np.uint8),
                            pixel_format="rgb24", source_shape=(2, 2))
    second = canonical_frame(np.zeros((3, 12), dtype=np.uint8),
                             pixel_format="rgb24", source_shape=(3, 4))
    with pytest.raises(NativeV2ValidationError, match="not followed by a key"):
        write_native_v2(tmp_path / "unkeyed.casu",
                        _manifest(_video_descriptor()), [
            NativeChunk(ChunkType.VIDEO_KEY_STATE, 1, 0,
                        encode_key_state(first)),
            NativeChunk(ChunkType.VIDEO_FORMAT_CHANGE, 1, 10,
                        encode_format_change(second)),
        ])


def test_dependency_depth_limit_is_enforced_by_writer_and_reader(tmp_path):
    base = canonical_frame(np.zeros((2, 6), dtype=np.uint8),
                           pixel_format="rgb24", source_shape=(2, 2))
    changed_pixels = np.zeros((2, 6), dtype=np.uint8)
    changed_pixels[0, :3] = 1
    changed = canonical_frame(changed_pixels, pixel_format="rgb24",
                              source_shape=(2, 2))
    update = encode_tile_update(changed, x=0, y=0, width=2, height=1)
    chunks = [NativeChunk(ChunkType.VIDEO_KEY_STATE, 1, 0,
                          encode_key_state(base)),
              NativeChunk(ChunkType.VIDEO_TILE_UPDATE, 1, 1, update),
              NativeChunk(ChunkType.VIDEO_TILE_UPDATE, 1, 2, update)]
    with pytest.raises(NativeV2ValidationError, match="dependency depth"):
        write_native_v2(tmp_path / "depth.casu", _manifest(_video_descriptor()),
                        chunks, limits=CasuLimits(max_dependency_depth=1),
                        recovery_interval=0)
    valid = tmp_path / "depth-two.casu"
    write_native_v2(valid, _manifest(_video_descriptor()), chunks,
                    limits=CasuLimits(max_dependency_depth=2),
                    recovery_interval=0)
    with pytest.raises(NativeV2Error, match="dependency depth"):
        read_native_v2(valid, limits=CasuLimits(max_dependency_depth=1))
