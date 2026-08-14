"""Lossless, timestamped CASUNAT2 audio block payloads."""
from __future__ import annotations

import json
import struct
import zlib
from dataclasses import dataclass

from .jsonutil import StrictJsonError, strict_json_loads

_U32 = struct.Struct(">I")


class AudioPayloadError(ValueError):
    pass


MAX_DECODED_AUDIO_BYTES = 256 * 1024 * 1024
MAX_AUDIO_METADATA_BYTES = 64 * 1024
MAX_AUDIO_CHANNELS = 64
MAX_AUDIO_SAMPLE_RATE = 768_000


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
    if (time_base_num <= 0 or time_base_den <= 0
            or sample_rate <= 0 or sample_rate > MAX_AUDIO_SAMPLE_RATE
            or channels <= 0 or channels > MAX_AUDIO_CHANNELS
            or sample_count < 0):
        raise AudioPayloadError("invalid audio timing or format")
    if not isinstance(pcm, (bytes, bytearray, memoryview)):
        raise AudioPayloadError("pcm must be bytes-like")
    raw = bytes(pcm)
    if (sample_format != "s16le" or len(raw) > MAX_DECODED_AUDIO_BYTES
            or len(raw) != sample_count * channels * 2):
        raise AudioPayloadError("PCM byte length does not match samples/channels/format")
    compressed = zlib.compress(raw, level=9)
    meta = {"pts": values[1], "time_base": [values[2], values[3]],
            "sample_rate": values[4], "channels": values[5],
            "channel_layout": channel_layout, "sample_format": values[6],
            "sample_count": values[7], "raw_length": len(raw),
            "compressed_length": len(compressed), "compression": "zlib"}
    header = json.dumps(meta, sort_keys=True, separators=(",", ":"),
                        allow_nan=False).encode("utf-8")
    return _U32.pack(len(header)) + header + compressed


def decode_audio_block(payload: bytes) -> AudioBlock:
    if len(payload) < _U32.size:
        raise AudioPayloadError("truncated audio block")
    length = _U32.unpack_from(payload)[0]
    if length > len(payload) - _U32.size or length > MAX_AUDIO_METADATA_BYTES:
        raise AudioPayloadError("invalid audio block metadata length")
    try:
        meta = strict_json_loads(payload[_U32.size:_U32.size + length])
        if meta.get("compression", "zlib") != "zlib":
            raise ValueError
        num, den = (int(v) for v in meta["time_base"])
        expected = int(meta["raw_length"])
        if expected < 0 or expected > MAX_DECODED_AUDIO_BYTES:
            raise AudioPayloadError("decoded audio block exceeds safety limit")
        decoder = zlib.decompressobj()
        raw = decoder.decompress(payload[_U32.size + length:], expected + 1)
        if len(raw) != expected or not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
            raise AudioPayloadError("audio block decompressed length mismatch")
        block = AudioBlock(int(meta["pts"]), num, den, int(meta["sample_rate"]),
                           int(meta["channels"]), meta.get("channel_layout"),
                           str(meta["sample_format"]), int(meta["sample_count"]), raw)
    except (KeyError, TypeError, ValueError, StrictJsonError, zlib.error) as exc:
        raise AudioPayloadError("invalid audio block") from exc
    if len(raw) != int(meta.get("raw_length", -1)) or len(payload) != _U32.size + length + int(meta.get("compressed_length", -1)):
        raise AudioPayloadError("audio block length mismatch")
    if (block.time_base_num <= 0 or block.time_base_den <= 0 or
            block.sample_rate <= 0 or block.sample_rate > MAX_AUDIO_SAMPLE_RATE
            or block.channels <= 0 or block.channels > MAX_AUDIO_CHANNELS):
        raise AudioPayloadError("invalid audio block format")
    if block.sample_format != "s16le" or len(raw) != block.sample_count * block.channels * 2:
        raise AudioPayloadError("audio PCM layout does not match sample metadata")
    return block
