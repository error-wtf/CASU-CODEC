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
class NativeV2Recovery:
    """Verified prefix that can be resumed after an interrupted write.

    Recovery deliberately does not claim full-container integrity: the
    trailing seek/integrity/END chunks may be absent after a crash.
    """
    path: Path
    manifest: dict
    chunks: tuple[NativeChunk, ...]
    recovery_point: dict
    complete_chunk_offset: int


@dataclass(frozen=True)
class NativeV2Container:
    path: Path
    manifest: dict
    chunks: tuple[NativeChunk, ...]
    offsets: tuple[int, ...]
    seek_entries: tuple[SeekEntry, ...]
    integrity_verified: bool
    recovery_points: tuple[dict, ...] = ()

    def chunks_at_or_after(self, pts: int, stream_id: int | None = None):
        return tuple(chunk for chunk in self.chunks
                     if (stream_id is None or chunk.stream_id == stream_id) and chunk.pts >= pts)


def read_native_v2(path: str | Path, *, max_manifest_bytes: int = 64 * 1024 * 1024,
                   max_chunk_bytes: int = 512 * 1024 * 1024,
                   max_chunks: int = 10_000_000,
                   max_file_bytes: int = 4 * 1024 * 1024 * 1024) -> NativeV2Container:
    source = Path(path)
    if source.stat().st_size > max_file_bytes:
        raise NativeV2Error("CASUNAT2 file exceeds configured size limit")
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
    recovery_points: list[dict] = []
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
        elif chunk_type == ChunkType.RECOVERY_POINT:
            try:
                recovery = json.loads(payload)
                if not isinstance(recovery, dict) or int(recovery.get("last_complete_chunk_offset", -1)) >= offset:
                    raise ValueError("invalid recovery offset")
                recovery_points.append(recovery)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise NativeV2Error("invalid CASUNAT2 recovery point") from exc
        if chunk_type == ChunkType.END:
            break
    if not chunks or chunks[-1].chunk_type != ChunkType.END:
        raise NativeV2Error("CASUNAT2 is missing END chunk")
    verified = False
    if integrity_expected is not None and integrity_offset is not None:
        verified = hashlib.sha256(raw[:integrity_offset]).hexdigest() == integrity_expected
        if not verified:
            raise NativeV2Error("CASUNAT2 integrity verification failed")
    return NativeV2Container(source, manifest, tuple(chunks), tuple(offsets), seek_entries, verified,
                             tuple(recovery_points))


def recover_native_v2(path: str | Path, *, max_manifest_bytes: int = 64 * 1024 * 1024,
                      max_chunk_bytes: int = 512 * 1024 * 1024,
                      max_chunks: int = 10_000_000) -> NativeV2Recovery:
    """Recover the last complete prefix from a truncated CASUNAT2 file.

    Only a writer-emitted RECOVERY_POINT is accepted as a resume boundary;
    arbitrary byte prefixes are never exposed as valid media state.
    """
    source = Path(path)
    raw = source.read_bytes()
    if len(raw) < HEADER.size:
        raise NativeV2Error("truncated CASUNAT2 header")
    magic, version, _flags, manifest_length = HEADER.unpack_from(raw)
    if magic != MAGIC or version != VERSION:
        raise NativeV2Error("unsupported CASUNAT2 header/version")
    if manifest_length > max_manifest_bytes or HEADER.size + manifest_length > len(raw):
        raise NativeV2Error("invalid CASUNAT2 manifest length")
    try:
        manifest = json.loads(raw[HEADER.size:HEADER.size + manifest_length])
    except json.JSONDecodeError as exc:
        raise NativeV2Error("invalid CASUNAT2 manifest") from exc
    pos = HEADER.size + manifest_length
    chunks: list[NativeChunk] = []
    recovery: tuple[dict, int] | None = None
    while pos + CHUNK_HEADER.size <= len(raw) and len(chunks) < max_chunks:
        offset = pos
        kind, stream_id, flags, pts, payload_length, uncompressed = CHUNK_HEADER.unpack_from(raw, pos)
        pos += CHUNK_HEADER.size
        if payload_length > max_chunk_bytes or payload_length > len(raw) - pos:
            break
        payload = raw[pos:pos + payload_length]; pos += payload_length
        try:
            chunk_type = ChunkType(kind)
        except ValueError:
            break
        chunk = NativeChunk(chunk_type, stream_id, pts, payload, flags, uncompressed)
        chunks.append(chunk)
        if chunk_type == ChunkType.RECOVERY_POINT:
            try:
                value = json.loads(payload)
                boundary = int(value["last_complete_chunk_offset"])
                if boundary < offset:
                    recovery = (value, boundary)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                break
    if recovery is None:
        raise NativeV2Error("CASUNAT2 contains no usable recovery point")
    value, boundary = recovery
    usable = tuple(chunk for chunk, chunk_offset in zip(chunks, _chunk_offsets(raw, manifest_length))
                   if chunk_offset <= boundary)
    return NativeV2Recovery(source, manifest, usable, value, boundary)


def _chunk_offsets(raw: bytes, manifest_length: int):
    pos = HEADER.size + manifest_length
    while pos + CHUNK_HEADER.size <= len(raw):
        offset = pos
        _kind, _stream, _flags, _pts, payload_length, _uncompressed = CHUNK_HEADER.unpack_from(raw, pos)
        pos += CHUNK_HEADER.size
        if payload_length > len(raw) - pos:
            break
        yield offset
        pos += payload_length
