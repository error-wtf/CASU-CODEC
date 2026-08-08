"""Lossless, timestamped CASUNAT2 audio block payloads."""
from __future__ import annotations

import json
import struct
import zlib
from dataclasses import dataclass

_U32 = struct.Struct(">I")


class AudioPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class AudioBlock:
    pts: int
    time_base_num: int
    time_base_den: int
    sample_rate: int
    channels: int
    channel_layout: str | None
    sample_format: str
    sample_count: int
    pcm: bytes


def encode_audio_block(*, pcm: bytes, pts: int, time_base_num: int, time_base_den: int,
                       sample_rate: int, channels: int, sample_format: str = "s16le",
                       channel_layout: str | None = None, sample_count: int) -> bytes:
    values = [pcm, int(pts), int(time_base_num), int(time_base_den), int(sample_rate),
              int(channels), str(sample_format), int(sample_count)]
    if time_base_den <= 0 or sample_rate <= 0 or channels <= 0 or sample_count < 0:
        raise AudioPayloadError("invalid audio timing or format")
    if not isinstance(pcm, (bytes, bytearray, memoryview)):
        raise AudioPayloadError("pcm must be bytes-like")
    raw = bytes(pcm)
    compressed = zlib.compress(raw, level=9)
    meta = {"pts": values[1], "time_base": [values[2], values[3]],
            "sample_rate": values[4], "channels": values[5],
            "channel_layout": channel_layout, "sample_format": values[6],
            "sample_count": values[7], "raw_length": len(raw),
            "compressed_length": len(compressed)}
    header = json.dumps(meta, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _U32.pack(len(header)) + header + compressed


def decode_audio_block(payload: bytes) -> AudioBlock:
    if len(payload) < _U32.size:
        raise AudioPayloadError("truncated audio block")
    length = _U32.unpack_from(payload)[0]
    if length > len(payload) - _U32.size:
        raise AudioPayloadError("invalid audio block metadata length")
    try:
        meta = json.loads(payload[_U32.size:_U32.size + length])
        raw = zlib.decompress(payload[_U32.size + length:])
        num, den = (int(v) for v in meta["time_base"])
        block = AudioBlock(int(meta["pts"]), num, den, int(meta["sample_rate"]),
                           int(meta["channels"]), meta.get("channel_layout"),
                           str(meta["sample_format"]), int(meta["sample_count"]), raw)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, zlib.error) as exc:
        raise AudioPayloadError("invalid audio block") from exc
    if len(raw) != int(meta.get("raw_length", -1)) or len(payload) != _U32.size + length + int(meta.get("compressed_length", -1)):
        raise AudioPayloadError("audio block length mismatch")
    if block.time_base_den <= 0 or block.sample_rate <= 0 or block.channels <= 0:
        raise AudioPayloadError("invalid audio block format")
    return block
