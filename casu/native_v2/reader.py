from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path

from .format import ChunkType, NativeChunk, SeekEntry
from .writer import CHUNK_HEADER, HEADER, MAGIC, VERSION


class NativeV2Error(ValueError):
    pass


@dataclass(frozen=True)
class NativeV2Container:
    path: Path
    manifest: dict
    chunks: tuple[NativeChunk, ...]
    offsets: tuple[int, ...]
    seek_entries: tuple[SeekEntry, ...]
    integrity_verified: bool

    def chunks_at_or_after(self, pts: int, stream_id: int | None = None):
        return tuple(chunk for chunk in self.chunks
                     if (stream_id is None or chunk.stream_id == stream_id) and chunk.pts >= pts)


def read_native_v2(path: str | Path, *, max_manifest_bytes: int = 64 * 1024 * 1024,
                   max_chunk_bytes: int = 512 * 1024 * 1024,
                   max_chunks: int = 10_000_000) -> NativeV2Container:
    source = Path(path)
    raw = source.read_bytes()
    if len(raw) < HEADER.size:
        raise NativeV2Error("truncated CASUNAT2 header")
    magic, version, _flags, manifest_length = HEADER.unpack_from(raw)
    if magic != MAGIC or version != VERSION:
        raise NativeV2Error("unsupported CASUNAT2 header/version")
    if manifest_length > max_manifest_bytes or HEADER.size + manifest_length > len(raw):
        raise NativeV2Error("invalid CASUNAT2 manifest length")
    start = HEADER.size
    try:
        manifest = json.loads(raw[start:start + manifest_length])
    except json.JSONDecodeError as exc:
        raise NativeV2Error("invalid CASUNAT2 manifest") from exc
    pos = start + manifest_length
    chunks: list[NativeChunk] = []
    offsets: list[int] = []
    seek_entries: tuple[SeekEntry, ...] = ()
    integrity_expected: str | None = None
    integrity_offset: int | None = None
    while pos < len(raw):
        if len(chunks) >= max_chunks or pos + CHUNK_HEADER.size > len(raw):
            raise NativeV2Error("truncated or excessive CASUNAT2 chunks")
        offset = pos
        kind, stream_id, flags, pts, payload_length, uncompressed = CHUNK_HEADER.unpack_from(raw, pos)
        pos += CHUNK_HEADER.size
        if payload_length > max_chunk_bytes or payload_length > len(raw) - pos:
            raise NativeV2Error("invalid CASUNAT2 chunk length")
        payload = raw[pos:pos + payload_length]
        pos += payload_length
        try:
            chunk_type = ChunkType(kind)
        except ValueError as exc:
            raise NativeV2Error(f"unknown CASUNAT2 chunk type {kind}") from exc
        chunks.append(NativeChunk(chunk_type, stream_id, pts, payload, flags, uncompressed))
        offsets.append(offset)
        if chunk_type == ChunkType.SEEK_INDEX:
            try:
                seek_entries = tuple(SeekEntry(**item) for item in json.loads(payload)["entries"])
            except (KeyError, TypeError, json.JSONDecodeError) as exc:
                raise NativeV2Error("invalid CASUNAT2 seek index") from exc
        elif chunk_type == ChunkType.INTEGRITY_TABLE:
            integrity_offset = offset
            try:
                integrity_expected = str(json.loads(payload)["sha256_before_integrity"])
            except (KeyError, TypeError, json.JSONDecodeError) as exc:
                raise NativeV2Error("invalid CASUNAT2 integrity table") from exc
        if chunk_type == ChunkType.END:
            break
    if not chunks or chunks[-1].chunk_type != ChunkType.END:
        raise NativeV2Error("CASUNAT2 is missing END chunk")
    verified = False
    if integrity_expected is not None and integrity_offset is not None:
        verified = hashlib.sha256(raw[:integrity_offset]).hexdigest() == integrity_expected
        if not verified:
            raise NativeV2Error("CASUNAT2 integrity verification failed")
    return NativeV2Container(source, manifest, tuple(chunks), tuple(offsets), seek_entries, verified)

