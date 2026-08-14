"""Convert media to CASU MP5 format."""
from __future__ import annotations

import tempfile
from pathlib import Path

from .format import ChunkType
from .writer import write_mp5, Mp5Error
from casu.core import analyze, ffprobe, sha256_file


def convert_to_mp5(source: str | Path, output: str | Path, *,
                   mode: str = "strict",
                   tile_width: int = 64, tile_height: int = 64,
                   key_interval_seconds: float = 3.0) -> Path:
    source = Path(source).expanduser().resolve()
    output = Path(output).expanduser().resolve()
    if not source.is_file():
        raise Mp5Error(f"source not found: {source}")
    probe = ffprobe(source)
    manifest = analyze(source, mode=mode)
    manifest["format"]["kind"] = "CASU MP5 enhanced container"
    manifest["format"]["mp5_version"] = 1
    manifest["source"]["sha256"] = sha256_file(source)
    chunks: list[tuple[ChunkType, int, int, bytes]] = []
    streams = probe.get("streams", [])
    for index, stream in enumerate(streams):
        st = {
            "stream_id": index,
            "type": stream.get("codec_type", "data"),
            "codec": stream.get("codec_name", "unknown"),
            "time_base": stream.get("time_base", "1/1000"),
        }
        chunks.append((ChunkType.STREAM_CONFIG, index, 0,
                       str(st).encode("utf-8")))
    chunks.append((ChunkType.METADATA, 0, 0,
                   str(manifest.get("source", {})).encode("utf-8")))
    chunks.append((ChunkType.INTEGRITY_TABLE, 0, 0,
                   sha256_file(source).encode("utf-8")))
    chunks.append((ChunkType.END, 0, 0, b""))
    return write_mp5(output, manifest, chunks)
