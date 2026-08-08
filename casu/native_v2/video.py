"""Lossless canonical video payloads used by CASUNAT2 key/update chunks."""
from __future__ import annotations

import json
import struct
import zlib
from dataclasses import dataclass

import numpy as np

from casu.strict.canonical import CanonicalFrame, canonical_frame

_U32 = struct.Struct(">I")


class VideoPayloadError(ValueError):
    pass


def _meta(frame: CanonicalFrame) -> dict:
    return {"pixel_format": frame.pixel_format, "source_shape": list(frame.shape),
            "color_metadata": dict(frame.color_metadata),
            "planes": [{"shape": list(plane.shape), "dtype": str(plane.dtype)}
                        for plane in frame.planes]}


def _pack(meta: dict, blobs: list[bytes]) -> bytes:
    header = json.dumps(meta, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _U32.pack(len(header)) + header + b"".join(blobs)


def _unpack(payload: bytes) -> tuple[dict, list[bytes]]:
    if len(payload) < _U32.size:
        raise VideoPayloadError("truncated video payload")
    length = _U32.unpack_from(payload)[0]
    if length > len(payload) - _U32.size:
        raise VideoPayloadError("invalid video payload header length")
    try:
        meta = json.loads(payload[_U32.size:_U32.size + length])
    except json.JSONDecodeError as exc:
        raise VideoPayloadError("invalid video payload metadata") from exc
    pos = _U32.size + length
    blobs = []
    for plane in meta.get("planes", []):
        compressed_length = int(plane.get("compressed_length", 0))
        if compressed_length < 0 or compressed_length > len(payload) - pos:
            raise VideoPayloadError("invalid compressed plane length")
        blobs.append(payload[pos:pos + compressed_length])
        pos += compressed_length
    if pos != len(payload):
        raise VideoPayloadError("trailing bytes in video payload")
    return meta, blobs


def encode_key_state(frame: CanonicalFrame) -> bytes:
    """Encode every active plane losslessly and deterministically."""
    meta = _meta(frame)
    blobs = []
    for index, plane in enumerate(frame.planes):
        compressed = zlib.compress(plane.tobytes(order="C"), level=9)
        meta["planes"][index]["raw_length"] = int(plane.nbytes)
        meta["planes"][index]["compressed_length"] = len(compressed)
        blobs.append(compressed)
    return _pack(meta, blobs)


def decode_key_state(payload: bytes) -> CanonicalFrame:
    meta, blobs = _unpack(payload)
    planes = []
    for descriptor, compressed in zip(meta["planes"], blobs):
        raw = zlib.decompress(compressed)
        if len(raw) != int(descriptor["raw_length"]):
            raise VideoPayloadError("decoded plane length mismatch")
        shape = tuple(int(value) for value in descriptor["shape"])
        array = np.frombuffer(raw, dtype=np.dtype(descriptor["dtype"])).reshape(shape).copy()
        planes.append(array)
    return canonical_frame(tuple(planes), pixel_format=str(meta["pixel_format"]),
                           source_shape=tuple(meta["source_shape"]),
                           color_metadata=meta.get("color_metadata", {}))


def _slice(plane: np.ndarray, frame: CanonicalFrame, x: int, y: int, w: int, h: int):
    ph, pw = plane.shape[:2]
    sh, sw = frame.shape
    x0, y0 = (x * pw) // sw, (y * ph) // sh
    x1 = max(x0 + 1, ((x + w) * pw + sw - 1) // sw)
    y1 = max(y0 + 1, ((y + h) * ph + sh - 1) // sh)
    return plane[y0:min(y1, ph), x0:min(x1, pw)]


def encode_tile_update(frame: CanonicalFrame, *, x: int, y: int, width: int, height: int) -> bytes:
    if min(x, y) < 0 or min(width, height) <= 0 or x + width > frame.shape[1] or y + height > frame.shape[0]:
        raise VideoPayloadError("tile is outside source frame")
    parts = [_slice(plane, frame, x, y, width, height) for plane in frame.planes]
    meta = {"pixel_format": frame.pixel_format, "source_shape": list(frame.shape),
            "color_metadata": dict(frame.color_metadata), "region": [x, y, width, height],
            "planes": [{"shape": list(part.shape), "dtype": str(part.dtype)} for part in parts]}
    blobs = []
    for index, part in enumerate(parts):
        compressed = zlib.compress(part.tobytes(order="C"), level=9)
        meta["planes"][index]["raw_length"] = int(part.nbytes)
        meta["planes"][index]["compressed_length"] = len(compressed)
        blobs.append(compressed)
    return _pack(meta, blobs)


@dataclass
class TileStateCache:
    """Reconstruct a source-resolution frame without legacy payload extraction."""
    frame: CanonicalFrame | None = None

    def apply_key_state(self, payload: bytes) -> CanonicalFrame:
        self.frame = decode_key_state(payload)
        return self.frame

    def apply_tile_update(self, payload: bytes) -> CanonicalFrame:
        if self.frame is None:
            raise VideoPayloadError("tile update requires a key state")
        meta, blobs = _unpack(payload)
        if tuple(meta["source_shape"]) != self.frame.shape or meta["pixel_format"] != self.frame.pixel_format:
            raise VideoPayloadError("tile update format differs from cached key state")
        x, y, width, height = (int(value) for value in meta["region"])
        planes = [plane.copy() for plane in self.frame.planes]
        for index, (descriptor, compressed) in enumerate(zip(meta["planes"], blobs)):
            raw = zlib.decompress(compressed)
            shape = tuple(int(value) for value in descriptor["shape"])
            tile = np.frombuffer(raw, dtype=np.dtype(descriptor["dtype"])).reshape(shape)
            target = planes[index]
            ph, pw = target.shape[:2]
            sh, sw = self.frame.shape
            x0, y0 = (x * pw) // sw, (y * ph) // sh
            x1 = max(x0 + 1, ((x + width) * pw + sw - 1) // sw)
            y1 = max(y0 + 1, ((y + height) * ph + sh - 1) // sh)
            if tile.shape != target[y0:min(y1, ph), x0:min(x1, pw)].shape:
                raise VideoPayloadError("tile plane shape mismatch")
            target[y0:min(y1, ph), x0:min(x1, pw)] = tile
        self.frame = canonical_frame(tuple(planes), pixel_format=self.frame.pixel_format,
                                     source_shape=self.frame.shape,
                                     color_metadata=dict(self.frame.color_metadata))
        return self.frame
