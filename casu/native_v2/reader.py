from __future__ import annotations

import hashlib
import json
import struct
import copy
from dataclasses import dataclass
from pathlib import Path

from .format import ChunkType, NativeChunk, SeekEntry
from .writer import CHUNK_HEADER, HEADER, MAGIC, VERSION, write_native_v2
from .video import TileStateCache


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
class ReconstructionPlan:
    stream_id: int
    target_pts: int
    key_state_pts: int
    key_state_offset: int
    first_update_offset: int


@dataclass(frozen=True)
class NativeV2Container:
    path: Path
    manifest: dict
    chunks: tuple[NativeChunk, ...]
    offsets: tuple[int, ...]
    seek_entries: tuple[SeekEntry, ...]
    integrity_verified: bool
    recovery_points: tuple[dict, ...] = ()
    chunk_hashes: tuple[tuple[int, str], ...] = ()

    def chunks_at_or_after(self, pts: int, stream_id: int | None = None):
        return tuple(chunk for chunk in self.chunks
                     if (stream_id is None or chunk.stream_id == stream_id) and chunk.pts >= pts)

    def read_chunk_at(self, offset: int) -> tuple[NativeChunk, int]:
        """Read one chunk using a real file seek, returning chunk and next offset."""
        size = self.path.stat().st_size
        if offset < HEADER.size or offset + CHUNK_HEADER.size > size:
            raise NativeV2Error("chunk offset is outside CASUNAT2 file")
        with self.path.open("rb") as handle:
            handle.seek(offset)
            header = handle.read(CHUNK_HEADER.size)
            if len(header) != CHUNK_HEADER.size:
                raise NativeV2Error("truncated chunk at indexed offset")
            kind, stream_id, flags, pts, payload_length, uncompressed = CHUNK_HEADER.unpack(header)
            if payload_length > size - handle.tell():
                raise NativeV2Error("indexed chunk payload exceeds file")
            payload = handle.read(payload_length)
        expected_hash = dict(self.chunk_hashes).get(offset)
        if expected_hash is not None and hashlib.sha256(header + payload).hexdigest() != expected_hash:
            raise NativeV2Error("on-disk CASUNAT2 chunk changed after verification")
        try:
            chunk_type = ChunkType(kind)
        except ValueError as exc:
            raise NativeV2Error("indexed chunk has unknown type") from exc
        return (NativeChunk(chunk_type, stream_id, pts, payload, flags, uncompressed),
                offset + CHUNK_HEADER.size + payload_length)

    def seek_video(self, stream_id: int, target_pts: int) -> ReconstructionPlan:
        candidates = [entry for entry in self.seek_entries
                      if entry.stream_id == stream_id and entry.key_state_pts <= target_pts]
        if not candidates:
            raise NativeV2Error("no video key state at or before target PTS")
        entry = max(candidates, key=lambda value: (value.key_state_pts,
                                                   value.key_state_offset))
        return ReconstructionPlan(stream_id, int(target_pts), entry.key_state_pts,
                                  entry.key_state_offset, entry.first_update_offset)

    def reconstruct_video(self, stream_id: int, target_pts: int):
        """Seek to a byte-indexed key state and apply dependencies through target."""
        plan = self.seek_video(stream_id, target_pts)
        cache = TileStateCache()
        offset = plan.key_state_offset
        first = True
        while offset < self.path.stat().st_size:
            chunk, following = self.read_chunk_at(offset)
            if chunk.stream_id == stream_id:
                if first:
                    if chunk.chunk_type != ChunkType.VIDEO_KEY_STATE or chunk.pts != plan.key_state_pts:
                        raise NativeV2Error("seek index does not reference its video key state")
                    cache.apply_key_state(chunk.payload)
                    first = False
                elif chunk.chunk_type == ChunkType.VIDEO_KEY_STATE:
                    if chunk.pts > target_pts:
                        break
                    cache.apply_key_state(chunk.payload)
                elif chunk.chunk_type == ChunkType.VIDEO_TILE_UPDATE:
                    if chunk.pts > target_pts:
                        break
                    cache.apply_tile_update(chunk.payload)
            if chunk.chunk_type in (ChunkType.SEEK_INDEX, ChunkType.INTEGRITY_TABLE,
                                    ChunkType.END):
                break
            offset = following
        if cache.frame is None:
            raise NativeV2Error("video reconstruction produced no frame")
        return cache.frame


def read_native_v2(path: str | Path, *, max_manifest_bytes: int = 64 * 1024 * 1024,
                   max_chunk_bytes: int = 512 * 1024 * 1024,
                   max_chunks: int = 10_000_000,
                   max_file_bytes: int = 4 * 1024 * 1024 * 1024,
                   load_payloads: bool = True) -> NativeV2Container:
    source = Path(path)
    size = source.stat().st_size
    if size > max_file_bytes:
        raise NativeV2Error("CASUNAT2 file exceeds configured size limit")
    chunks: list[NativeChunk] = []
    offsets: list[int] = []
    seek_entries: tuple[SeekEntry, ...] = ()
    integrity_expected: str | None = None
    integrity_offset: int | None = None
    recovery_points: list[dict] = []
    chunk_hashes: tuple[tuple[int, str], ...] = ()
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        header = handle.read(HEADER.size)
        if len(header) != HEADER.size:
            raise NativeV2Error("truncated CASUNAT2 header")
        magic, version, _flags, manifest_length = HEADER.unpack(header)
        if magic != MAGIC or version != VERSION:
            raise NativeV2Error("unsupported CASUNAT2 header/version")
        if manifest_length > max_manifest_bytes or manifest_length > size - HEADER.size:
            raise NativeV2Error("invalid CASUNAT2 manifest length")
        manifest_bytes = handle.read(manifest_length)
        if len(manifest_bytes) != manifest_length:
            raise NativeV2Error("truncated CASUNAT2 manifest")
        try:
            manifest = json.loads(manifest_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise NativeV2Error("invalid CASUNAT2 manifest") from exc
        digest.update(header); digest.update(manifest_bytes)
        seen_integrity = False
        while handle.tell() < size:
            if len(chunks) >= max_chunks:
                raise NativeV2Error("excessive CASUNAT2 chunks")
            offset = handle.tell()
            chunk_header = handle.read(CHUNK_HEADER.size)
            if len(chunk_header) != CHUNK_HEADER.size:
                raise NativeV2Error("truncated CASUNAT2 chunk header")
            kind, stream_id, flags, pts, payload_length, uncompressed = CHUNK_HEADER.unpack(chunk_header)
            if payload_length > max_chunk_bytes or payload_length > size - handle.tell():
                raise NativeV2Error("invalid CASUNAT2 chunk length")
            payload = handle.read(payload_length)
            if len(payload) != payload_length:
                raise NativeV2Error("truncated CASUNAT2 chunk payload")
            try:
                chunk_type = ChunkType(kind)
            except ValueError as exc:
                raise NativeV2Error(f"unknown CASUNAT2 chunk type {kind}") from exc
            if seen_integrity and chunk_type != ChunkType.END:
                raise NativeV2Error("CASUNAT2 contains data after integrity table")
            if chunk_type == ChunkType.INTEGRITY_TABLE:
                if seen_integrity:
                    raise NativeV2Error("duplicate CASUNAT2 integrity table")
                seen_integrity = True
            elif not seen_integrity:
                digest.update(chunk_header); digest.update(payload)
            stored_payload = payload if load_payloads or chunk_type in {
                ChunkType.SEEK_INDEX, ChunkType.INTEGRITY_TABLE,
                ChunkType.RECOVERY_POINT, ChunkType.END,
            } else b""
            chunks.append(NativeChunk(chunk_type, stream_id, pts, stored_payload,
                                      flags, uncompressed))
            offsets.append(offset)
            if chunk_type == ChunkType.SEEK_INDEX:
                try:
                    values = json.loads(payload)["entries"]
                    if not isinstance(values, list) or len(values) > max_chunks:
                        raise TypeError("invalid seek entries")
                    seek_entries = tuple(SeekEntry(**item) for item in values)
                except (KeyError, TypeError, ValueError, json.JSONDecodeError,
                        UnicodeDecodeError) as exc:
                    raise NativeV2Error("invalid CASUNAT2 seek index") from exc
            elif chunk_type == ChunkType.INTEGRITY_TABLE:
                integrity_offset = offset
                try:
                    integrity_values = json.loads(payload)
                    integrity_expected = str(integrity_values["sha256_before_integrity"])
                    hashes = integrity_values.get("chunk_sha256", [])
                    if not isinstance(hashes, list) or len(hashes) > max_chunks:
                        raise TypeError("invalid chunk hash table")
                    chunk_hashes = tuple((int(item["offset"]), str(item["sha256"]))
                                         for item in hashes)
                    if any(offset < HEADER.size or len(value) != 64
                           for offset, value in chunk_hashes):
                        raise ValueError("invalid chunk hash")
                except (KeyError, TypeError, json.JSONDecodeError,
                        UnicodeDecodeError, ValueError) as exc:
                    raise NativeV2Error("invalid CASUNAT2 integrity table") from exc
            elif chunk_type == ChunkType.RECOVERY_POINT:
                try:
                    recovery = json.loads(payload)
                    if not isinstance(recovery, dict) or int(recovery.get("last_complete_chunk_offset", -1)) >= offset:
                        raise ValueError("invalid recovery offset")
                    recovery_points.append(recovery)
                except (TypeError, ValueError, json.JSONDecodeError,
                        UnicodeDecodeError) as exc:
                    raise NativeV2Error("invalid CASUNAT2 recovery point") from exc
            if chunk_type == ChunkType.END:
                if handle.tell() != size:
                    raise NativeV2Error("trailing bytes after CASUNAT2 END")
                break
    if not chunks or chunks[-1].chunk_type != ChunkType.END:
        raise NativeV2Error("CASUNAT2 is missing END chunk")
    verified = False
    if integrity_expected is None or integrity_offset is None:
        raise NativeV2Error("CASUNAT2 is missing integrity table")
    verified = digest.hexdigest() == integrity_expected
    if not verified:
        raise NativeV2Error("CASUNAT2 integrity verification failed")
    offset_map = dict(zip(offsets, chunks))
    previous_by_stream: dict[int, tuple[int, int]] = {}
    for entry in seek_entries:
        key = offset_map.get(entry.key_state_offset)
        first_update = offset_map.get(entry.first_update_offset)
        if (key is None or key.chunk_type != ChunkType.VIDEO_KEY_STATE
                or key.stream_id != entry.stream_id or key.pts != entry.key_state_pts):
            raise NativeV2Error("CASUNAT2 seek index key-state offset is invalid")
        if (first_update is None or first_update.stream_id != entry.stream_id
                or first_update.chunk_type not in (ChunkType.VIDEO_KEY_STATE,
                                                   ChunkType.VIDEO_TILE_UPDATE)):
            raise NativeV2Error("CASUNAT2 seek index dependency offset is invalid")
        prior = previous_by_stream.get(entry.stream_id)
        marker = (entry.key_state_pts, entry.key_state_offset)
        if prior is not None and marker <= prior:
            raise NativeV2Error("CASUNAT2 seek index is not strictly ordered")
        previous_by_stream[entry.stream_id] = marker
    expected_offsets = {offset for offset, chunk in zip(offsets, chunks)
                        if chunk.chunk_type not in {ChunkType.INTEGRITY_TABLE, ChunkType.END}}
    if chunk_hashes and ({offset for offset, _value in chunk_hashes} != expected_offsets
                         or len(dict(chunk_hashes)) != len(chunk_hashes)):
        raise NativeV2Error("CASUNAT2 chunk hash table does not cover the verified prefix")
    return NativeV2Container(source, manifest, tuple(chunks), tuple(offsets), seek_entries, verified,
                             tuple(recovery_points), chunk_hashes)


def recover_native_v2(path: str | Path, *, max_manifest_bytes: int = 64 * 1024 * 1024,
                      max_chunk_bytes: int = 512 * 1024 * 1024,
                      max_chunks: int = 10_000_000,
                      max_file_bytes: int = 512 * 1024 * 1024) -> NativeV2Recovery:
    """Recover the last complete prefix from a truncated CASUNAT2 file.

    Only a writer-emitted RECOVERY_POINT is accepted as a resume boundary;
    arbitrary byte prefixes are never exposed as valid media state.
    """
    source = Path(path)
    if source.stat().st_size > max_file_bytes:
        raise NativeV2Error("damaged CASUNAT2 file exceeds recovery size limit")
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


def repair_native_v2(source: str | Path, target: str | Path) -> Path:
    """Finalize the last declared complete prefix into a new verified file."""
    recovery = recover_native_v2(source)
    destination = Path(target).expanduser().resolve()
    original = recovery.path.expanduser().resolve()
    if destination == original:
        raise NativeV2Error("repair output must differ from the damaged source")
    manifest = copy.deepcopy(recovery.manifest)
    manifest["recovery"] = {
        "status": "RECOVERED_PREFIX",
        "source_filename": original.name,
        "last_complete_chunk_offset": recovery.complete_chunk_offset,
    }
    return write_native_v2(destination, manifest, recovery.chunks,
                           recovery_interval=0)


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
