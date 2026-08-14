from __future__ import annotations

import hashlib
import json
import os
import struct
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from .format import (DEFAULT_LIMITS, CasuLimits, ChunkType, NativeChunk,
                     SeekEntry)
from .validation import NativeV2PayloadValidator, NativeV2ValidationError
from .jsonutil import StrictJsonError, strict_json_loads

MAGIC = b"CASUNAT2"
VERSION = 2
HEADER = struct.Struct(">8sHHQ")
CHUNK_HEADER = struct.Struct(">BBHqQQ")


def _pack_chunk(chunk: NativeChunk) -> bytes:
    payload = bytes(chunk.payload)
    if chunk.stream_id < 0 or chunk.stream_id > 255:
        raise ValueError("stream_id must fit in uint8")
    if chunk.flags < 0 or chunk.flags > 65535:
        raise ValueError("flags must fit in uint16")
    uncompressed = len(payload) if chunk.uncompressed_length is None else int(chunk.uncompressed_length)
    if uncompressed < len(payload):
        raise ValueError("uncompressed_length cannot be below payload length")
    return CHUNK_HEADER.pack(int(chunk.chunk_type), chunk.stream_id, chunk.flags,
                             int(chunk.pts), len(payload), uncompressed) + payload


def _index_payload(entries: list[SeekEntry]) -> bytes:
    return json.dumps({"version": 1, "entries": [entry.__dict__ for entry in entries]},
                      sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def write_native_v2(path: str | Path, manifest: dict, chunks: Iterable[NativeChunk], *,
                    max_chunk_bytes: int = 512 * 1024 * 1024,
                    recovery_interval: int = 32,
                    limits: CasuLimits | None = None) -> Path:
    """Write a deterministic standalone CASUNAT2 file atomically."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    effective_limits = limits or replace(DEFAULT_LIMITS,
                                         max_chunk_bytes=max_chunk_bytes)
    effective_limits.validate()
    validator = NativeV2PayloadValidator(manifest, effective_limits,
                                         semantic=True)
    manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                                allow_nan=False).encode("utf-8")
    if len(manifest_bytes) > effective_limits.max_manifest_bytes:
        raise ValueError("manifest exceeds CASUNAT2 limit")
    seek: list[SeekEntry] = []
    with tempfile.NamedTemporaryFile(prefix=f".{target.name}.", dir=target.parent,
                                     delete=False) as handle:
        temporary = Path(handle.name)
        try:
            header = HEADER.pack(MAGIC, VERSION, 0, len(manifest_bytes))
            if len(header) + len(manifest_bytes) > effective_limits.max_file_bytes:
                raise ValueError("CASUNAT2 header/manifest exceeds file limit")
            handle.write(header)
            handle.write(manifest_bytes)
            prefix_digest = hashlib.sha256(header + manifest_bytes)
            written_chunk_count = 0

            def append_chunk(packed: bytes) -> None:
                nonlocal written_chunk_count
                payload_size = len(packed) - CHUNK_HEADER.size
                if (written_chunk_count >= effective_limits.max_chunks
                        or payload_size < 0
                        or payload_size > effective_limits.max_chunk_bytes
                        or handle.tell() + len(packed) > effective_limits.max_file_bytes):
                    raise ValueError("CASUNAT2 output exceeds configured limits")
                handle.write(packed)
                written_chunk_count += 1
            key_states: dict[int, tuple[int, int]] = {}
            seek_positions: dict[int, int] = {}
            if recovery_interval < 0:
                raise ValueError("recovery_interval must be non-negative")
            key_offsets: dict[int, int] = {}
            audio_offsets: dict[int, int] = {}
            chunk_hashes: list[dict[str, int | str]] = []
            # The manifest stream table and in-band stream configuration must
            # never drift. The writer emits one canonical config per stream so
            # every newly written CASUNAT2 file is self-describing even when a
            # low-level caller supplies only media chunks.
            for stream_id, descriptor in sorted(
                    validator.descriptors.items()):
                config_payload = json.dumps(
                    descriptor, sort_keys=True, separators=(",", ":"),
                    allow_nan=False).encode("utf-8")
                config = NativeChunk(ChunkType.STREAM_CONFIG, stream_id, 0,
                                     config_payload)
                validator.feed(config, allow_system=False)
                config_offset = handle.tell()
                config_packed = _pack_chunk(config)
                append_chunk(config_packed)
                prefix_digest.update(config_packed)
                chunk_hashes.append({
                    "offset": config_offset,
                    "sha256": hashlib.sha256(config_packed).hexdigest(),
                })
            for ordinal, chunk in enumerate(chunks, start=1):
                if ordinal > effective_limits.max_chunks:
                    raise ValueError("chunk count exceeds CASUNAT2 limit")
                if len(chunk.payload) > effective_limits.max_chunk_bytes:
                    raise ValueError("chunk exceeds CASUNAT2 limit")
                if chunk.chunk_type == ChunkType.STREAM_CONFIG:
                    try:
                        configured = strict_json_loads(chunk.payload)
                    except StrictJsonError as exc:
                        raise NativeV2ValidationError(
                            "invalid supplied stream config") from exc
                    if configured != validator.descriptors.get(chunk.stream_id):
                        raise NativeV2ValidationError(
                            "supplied stream config differs from manifest")
                    continue
                validator.feed(chunk, allow_system=False)
                offset = handle.tell()
                packed = _pack_chunk(chunk)
                append_chunk(packed)
                prefix_digest.update(packed)
                chunk_hashes.append({"offset": offset,
                                     "sha256": hashlib.sha256(packed).hexdigest()})
                if chunk.chunk_type == ChunkType.VIDEO_KEY_STATE:
                    key_states[chunk.stream_id] = (chunk.pts, offset)
                    key_offsets[chunk.stream_id] = offset
                    seek_positions[chunk.stream_id] = len(seek)
                    seek.append(SeekEntry(chunk.stream_id, chunk.pts, chunk.pts,
                                          offset, offset))
                elif chunk.chunk_type == ChunkType.VIDEO_TILE_UPDATE:
                    position = seek_positions.get(chunk.stream_id)
                    if position is None:
                        raise ValueError("video tile update precedes its key state")
                    entry = seek[position]
                    if entry.first_update_offset == entry.key_state_offset:
                        seek[position] = SeekEntry(entry.stream_id, entry.target_pts,
                                                   entry.key_state_pts,
                                                   entry.key_state_offset, offset)
                elif chunk.chunk_type == ChunkType.AUDIO_BLOCK:
                    audio_offsets[chunk.stream_id] = offset
                if recovery_interval and ordinal % recovery_interval == 0:
                    recovery = {"version": 1, "last_complete_chunk_offset": offset,
                                "key_state_offsets": dict(sorted(key_offsets.items())),
                                "audio_block_offsets": dict(sorted(audio_offsets.items())),
                                "sha256_before_recovery": prefix_digest.hexdigest()}
                    checkpoint = json.dumps(
                        recovery, sort_keys=True, separators=(",", ":"),
                        allow_nan=False
                    ).encode("utf-8")
                    recovery["checkpoint_sha256"] = hashlib.sha256(
                        checkpoint).hexdigest()
                    recovery_packed = _pack_chunk(NativeChunk(
                        ChunkType.RECOVERY_POINT, 0, chunk.pts,
                        json.dumps(recovery, sort_keys=True, separators=(",", ":"),
                                   allow_nan=False).encode("utf-8")))
                    recovery_offset = handle.tell()
                    append_chunk(recovery_packed)
                    prefix_digest.update(recovery_packed)
                    chunk_hashes.append({"offset": recovery_offset,
                                         "sha256": hashlib.sha256(recovery_packed).hexdigest()})
            validator.finalize(require_system=False)
            seek.sort(key=lambda entry: (entry.stream_id, entry.key_state_pts,
                                         entry.key_state_offset))
            index_offset = handle.tell()
            index_packed = _pack_chunk(NativeChunk(ChunkType.SEEK_INDEX, 0, 0,
                                                   _index_payload(seek)))
            append_chunk(index_packed)
            prefix_digest.update(index_packed)
            chunk_hashes.append({"offset": index_offset,
                                 "sha256": hashlib.sha256(index_packed).hexdigest()})
            digest = prefix_digest.hexdigest()
            append_chunk(_pack_chunk(NativeChunk(
                ChunkType.INTEGRITY_TABLE, 0, index_offset,
                json.dumps({"sha256_before_integrity": digest,
                            "chunk_sha256": chunk_hashes},
                           sort_keys=True, separators=(",", ":"),
                           allow_nan=False).encode("utf-8"))))
            append_chunk(_pack_chunk(NativeChunk(ChunkType.END, 0, 0, b"")))
            handle.flush()
            os.fsync(handle.fileno())
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, target)
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_fd = os.open(target.parent, directory_flags)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return target
