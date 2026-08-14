"""CASU MP5 reader with zstd decompression."""
from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

try:
    import zstd
except ImportError:
    zstd = None

from .format import (CHUNK_HEADER, FOOTER_SIZE, HEADER, MAGIC, VERSION,
                     ChunkType, MAX_CHUNK_PAYLOAD, SeekEntry)


class Mp5Error(ValueError):
    pass


@dataclass
class Mp5Container:
    path: Path
    manifest: dict
    chunks: list[tuple]
    size: int

    def read_chunk_at(self, offset: int) -> tuple:
        with self.path.open("rb") as handle:
            handle.seek(offset)
            raw = handle.read(CHUNK_HEADER.size)
            if len(raw) < CHUNK_HEADER.size:
                raise Mp5Error("truncated chunk header")
            chunk_type, stream_id, pts, comp_length = CHUNK_HEADER.unpack(raw)
            comp = handle.read(comp_length)
            if len(comp) < comp_length:
                raise Mp5Error("truncated chunk payload")
            payload = _decompress(comp)
            return ChunkType(chunk_type), stream_id, pts, payload


def _decompress(data: bytes) -> bytes:
    if zstd is not None:
        try:
            return zstd.decompress(data)
        except zstd.Error:
            pass
    import zlib
    return zlib.decompress(data)


def read_mp5(path: str | Path) -> Mp5Container:
    source = Path(path).expanduser().resolve()
    size = source.stat().st_size
    with source.open("rb") as handle:
        raw = handle.read(HEADER.size)
        if len(raw) < HEADER.size:
            raise Mp5Error("file too small for MP5 header")
        magic, version, flags, manifest_length, _reserved = HEADER.unpack(raw)
        if magic != MAGIC:
            raise Mp5Error(f"not a CASU MP5 file (magic={magic!r})")
        if version != VERSION:
            raise Mp5Error(f"unsupported MP5 version {version}")
        manifest_raw = handle.read(manifest_length)
        if len(manifest_raw) < manifest_length:
            raise Mp5Error("truncated manifest")
        manifest = json.loads(manifest_raw.decode("utf-8"))
        chunks = []
        while True:
            pos = handle.tell()
            head = handle.read(CHUNK_HEADER.size)
            if len(head) < CHUNK_HEADER.size:
                break
            chunk_type, stream_id, pts, comp_length = CHUNK_HEADER.unpack(head)
            ct = ChunkType(chunk_type)
            if ct == ChunkType.END:
                break
            chunks.append((ct, stream_id, pts, comp_length, pos))
            handle.seek(pos + CHUNK_HEADER.size + comp_length)
    return Mp5Container(source, manifest, tuple(chunks), size)
