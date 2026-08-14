# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Convert media into a playable CASU MP5 container.

MP5 is the enhanced CASU envelope: zstd-compressed chunks, JSON stream
configuration, a verified copy of the original source carried in ATTACHMENT
chunks (split below the chunk payload limit), an INTEGRITY_TABLE with
SHA-256 coverage and a footer digest over the manifest.  A `.mp5` produced
here is content-detected, verified and playable by extraction, mirroring the
CASUNAT1 compatibility envelope while using the MP5 chunk topology.
"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

from .format import ChunkType, MAX_CHUNK_PAYLOAD
from .writer import write_mp5, Mp5Error
from casu.core import ffprobe, sha256_file

ATTACHMENT_PART_BYTES = min(48 * 1024 * 1024, MAX_CHUNK_PAYLOAD)


def _attachment_payload(name: str, part_index: int, part_count: int,
                        data: bytes) -> bytes:
    meta = json.dumps({"filename": name, "part": part_index,
                       "parts": part_count},
                      sort_keys=True, separators=(",", ":")).encode("utf-8")
    return struct.pack("<H", len(meta)) + meta + data


def _bounded_manifest(probe: dict, mode: str) -> dict:
    """MP5 envelopes carry the verified original source, so the manifest stays
    bounded to container/stream metadata instead of a full temporal analysis."""
    probe_format = probe.get("format") if isinstance(probe.get("format"), dict) else {}
    probe_streams = probe.get("streams") if isinstance(probe.get("streams"), list) else []
    streams: list[dict] = []
    for index, stream in enumerate(probe_streams):
        if not isinstance(stream, dict):
            continue
        streams.append({"index": index,
                        "type": stream.get("codec_type"),
                        "codec": stream.get("codec_name"),
                        "width": stream.get("width"),
                        "height": stream.get("height"),
                        "sample_rate": stream.get("sample_rate"),
                        "channels": stream.get("channels")})
    return {"format": {"kind": "CASU MP5 enhanced container",
                       "mp5_version": 1,
                       "format_name": probe_format.get("format_name"),
                       "duration": probe_format.get("duration")},
            "source": {},
            "streams": streams,
            "analysis": {"mode": mode,
                         "note": "MP5 carries the SHA-256 verified original source; "
                                 "temporal state analysis is not embedded"}}


def convert_to_mp5(source: str | Path, output: str | Path, *,
                   mode: str = "strict",
                   tile_width: int = 64, tile_height: int = 64,
                   key_interval_seconds: float = 3.0) -> Path:
    source = Path(source).expanduser().resolve()
    output = Path(output).expanduser().resolve()
    if not source.is_file():
        raise Mp5Error(f"source not found: {source}")
    probe = ffprobe(source)
    manifest = _bounded_manifest(probe, mode)
    source_digest = sha256_file(source)
    manifest["source"]["sha256"] = source_digest
    manifest["source"]["filename"] = source.name
    manifest["source"]["bytes"] = source.stat().st_size

    chunks: list[tuple[ChunkType, int, int, bytes]] = []
    for index, stream in enumerate(probe.get("streams", [])):
        if not isinstance(stream, dict):
            continue
        config = {"stream_id": index,
                  "type": stream.get("codec_type", "data"),
                  "codec": stream.get("codec_name"),
                  "width": stream.get("width"),
                  "height": stream.get("height"),
                  "sample_rate": stream.get("sample_rate"),
                  "channels": stream.get("channels")}
        chunks.append((ChunkType.STREAM_CONFIG, index, 0,
                       json.dumps(config, sort_keys=True,
                                  separators=(",", ":")).encode("utf-8")))

    size = source.stat().st_size
    part_count = max(1, (size + ATTACHMENT_PART_BYTES - 1) // ATTACHMENT_PART_BYTES)
    attachment_digest = hashlib.sha256()
    with source.open("rb") as handle:
        for part in range(part_count):
            chunk_data = handle.read(ATTACHMENT_PART_BYTES)
            attachment_digest.update(chunk_data)
            chunks.append((ChunkType.ATTACHMENT, 0, part,
                           _attachment_payload(source.name, part, part_count, chunk_data)))

    integrity = {"source_sha256": source_digest,
                 "attachment_sha256": attachment_digest.hexdigest(),
                 "attachment_parts": part_count,
                 "chunk_count": len(chunks)}
    chunks.append((ChunkType.INTEGRITY_TABLE, 0, 0,
                   json.dumps(integrity, sort_keys=True,
                              separators=(",", ":")).encode("utf-8")))
    chunks.append((ChunkType.METADATA, 0, 0,
                   json.dumps({"converted_by": "casu.mp5", "mode": mode,
                               "tile_width": tile_width,
                               "tile_height": tile_height,
                               "key_interval_seconds": key_interval_seconds},
                              sort_keys=True, separators=(",", ":")).encode("utf-8")))
    chunks.append((ChunkType.END, 0, 0, b""))
    return write_mp5(output, manifest, chunks)
