from __future__ import annotations

import hashlib
import json
import os
import struct
import tempfile
from pathlib import Path
from typing import Iterable

from .format import ChunkType, NativeChunk, SeekEntry

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
                      sort_keys=True, separators=(",", ":")).encode("utf-8")


def write_native_v2(path: str | Path, manifest: dict, chunks: Iterable[NativeChunk], *,
                    max_chunk_bytes: int = 512 * 1024 * 1024) -> Path:
    """Write a deterministic standalone CASUNAT2 file atomically."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(manifest_bytes) > 64 * 1024 * 1024:
        raise ValueError("manifest exceeds CASUNAT2 limit")
    values = list(chunks)
    seek: list[SeekEntry] = []
    with tempfile.NamedTemporaryFile(prefix=f".{target.name}.", dir=target.parent,
                                     delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(HEADER.pack(MAGIC, VERSION, 0, len(manifest_bytes)))
            handle.write(manifest_bytes)
            key_states: dict[int, tuple[int, int]] = {}
            pending_updates: dict[int, int] = {}
            for chunk in values:
                if len(chunk.payload) > max_chunk_bytes:
                    raise ValueError("chunk exceeds CASUNAT2 limit")
                offset = handle.tell()
                handle.write(_pack_chunk(chunk))
                if chunk.chunk_type == ChunkType.VIDEO_KEY_STATE:
                    key_states[chunk.stream_id] = (chunk.pts, offset)
                    pending_updates.pop(chunk.stream_id, None)
                elif chunk.chunk_type == ChunkType.VIDEO_TILE_UPDATE:
                    pending_updates.setdefault(chunk.stream_id, offset)
                if chunk.chunk_type in (ChunkType.VIDEO_KEY_STATE, ChunkType.VIDEO_TILE_UPDATE):
                    key = key_states.get(chunk.stream_id)
                    if key:
                        seek.append(SeekEntry(chunk.stream_id, chunk.pts, key[0], key[1],
                                              pending_updates.get(chunk.stream_id, offset)))
            # Keep one deterministic entry per key state/stream.
            unique = {(entry.stream_id, entry.key_state_offset): entry for entry in seek}
            index_offset = handle.tell()
            handle.write(_pack_chunk(NativeChunk(ChunkType.SEEK_INDEX, 0, 0,
                                                 _index_payload(list(unique.values())))))
            handle.flush()
            handle.seek(0)
            digest = hashlib.sha256(handle.read()).hexdigest().encode("ascii")
            handle.seek(0, os.SEEK_END)
            handle.write(_pack_chunk(NativeChunk(ChunkType.INTEGRITY_TABLE, 0, index_offset,
                                                 json.dumps({"sha256_before_integrity": digest.decode()},
                                                            sort_keys=True).encode("utf-8"))))
            handle.write(_pack_chunk(NativeChunk(ChunkType.END, 0, 0, b"")))
            handle.flush()
            os.fsync(handle.fileno())
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    os.replace(temporary, target)
    return target

