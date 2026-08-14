"""CASU MP5 writer with zstd compression."""
from __future__ import annotations

import hashlib
import json
import os
import struct
import tempfile
from pathlib import Path

try:
    import zstd
except ImportError:
    zstd = None

from .format import (CHUNK_HEADER, FOOTER_SIZE, HEADER, MAGIC, VERSION,
                     ChunkType, MAX_CHUNK_PAYLOAD, MAX_MANIFEST_BYTES)


class Mp5Error(ValueError):
    pass


def _compress(data: bytes) -> bytes:
    if zstd is not None:
        return zstd.compress(data, 3)
    import zlib
    return zlib.compress(data, level=3)


def _write_chunk(target, chunk_type: ChunkType, stream_id: int, pts: int, payload: bytes) -> int:
    comp = _compress(payload)
    if len(comp) > MAX_CHUNK_PAYLOAD:
        raise Mp5Error("compressed chunk exceeds size limit")
    header = CHUNK_HEADER.pack(int(chunk_type), int(stream_id), int(pts), len(comp))
    target.write(header)
    target.write(comp)
    return len(header) + len(comp)


def write_mp5(output: Path, manifest: dict, chunks: list[tuple[ChunkType, int, int, bytes]]) -> Path:
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise Mp5Error("manifest exceeds size limit")
    manifest_digest = hashlib.sha256(manifest_bytes).digest()
    fd, tmp = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    try:
        with os.fdopen(fd, "wb") as target:
            header_data = HEADER.pack(MAGIC, VERSION, 0, len(manifest_bytes), 0)
            target.write(header_data)
            target.write(manifest_bytes)
            for chunk_type, stream_id, pts, payload in chunks:
                if chunk_type == ChunkType.END:
                    target.write(CHUNK_HEADER.pack(int(ChunkType.END), 0, 0, 0))
                else:
                    _write_chunk(target, chunk_type, stream_id, pts, payload)
            footer = struct.pack("<I32s", len(chunks), manifest_digest)
            target.write(footer)
            target.flush()
            os.fsync(target.fileno())
        os.replace(tmp, output)
        return output
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
