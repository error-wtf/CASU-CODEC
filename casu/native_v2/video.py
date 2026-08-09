"""Lossless canonical video payloads used by CASUNAT2 key/update chunks."""
from __future__ import annotations

import json
import struct
import zlib
from dataclasses import dataclass

import numpy as np

from casu.strict.canonical import CanonicalFrame, PlaneLayout, canonical_frame
from casu.strict.tiles import canonical_tile_hash

_U32 = struct.Struct(">I")


class VideoPayloadError(ValueError):
    pass


MAX_DECODED_PLANE_BYTES = 512 * 1024 * 1024


def _decompress_exact(compressed: bytes, expected: int) -> bytes:
    if expected < 0 or expected > MAX_DECODED_PLANE_BYTES:
        raise VideoPayloadError("decoded video plane exceeds safety limit")
    decoder = zlib.decompressobj()
    try:
        raw = decoder.decompress(compressed, expected + 1)
    except zlib.error as exc:
        raise VideoPayloadError("invalid compressed video plane") from exc
    if (len(raw) != expected or not decoder.eof or decoder.unconsumed_tail
            or decoder.unused_data):
        raise VideoPayloadError("decoded plane length mismatch")
    return raw


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
        shape = tuple(int(value) for value in descriptor["shape"])
        if len(shape) != 2 or any(value <= 0 for value in shape):
            raise VideoPayloadError("invalid decoded plane shape")
        dtype = np.dtype(descriptor["dtype"])
        if dtype.kind != "u" or dtype.itemsize not in (1, 2):
            raise VideoPayloadError("invalid decoded plane dtype")
        expected = int(np.prod(shape, dtype=np.int64)) * dtype.itemsize
        if expected != int(descriptor["raw_length"]):
            raise VideoPayloadError("video plane metadata length mismatch")
        raw = _decompress_exact(compressed, expected)
        array = np.frombuffer(raw, dtype=dtype).reshape(shape).copy()
        planes.append(array)
    return canonical_frame(tuple(planes), pixel_format=str(meta["pixel_format"]),
                           source_shape=tuple(meta["source_shape"]),
                           color_metadata=meta.get("color_metadata", {}))


def _bounds(layout: PlaneLayout, x: int, y: int, w: int, h: int):
    x0 = (x >> layout.subsample_x) * layout.components
    y0 = y >> layout.subsample_y
    x1 = ((x + w + (1 << layout.subsample_x) - 1) >> layout.subsample_x) * layout.components
    y1 = (y + h + (1 << layout.subsample_y) - 1) >> layout.subsample_y
    return x0, y0, x1, y1


def _slice(plane: np.ndarray, layout: PlaneLayout, x: int, y: int, w: int, h: int):
    x0, y0, x1, y1 = _bounds(layout, x, y, w, h)
    return plane[y0:min(y1, plane.shape[0]), x0:min(x1, plane.shape[1])]


def encode_tile_update(frame: CanonicalFrame, *, x: int, y: int, width: int, height: int,
                       base_state_hash: str | None = None,
                       new_state_hash: str | None = None) -> bytes:
    if min(x, y) < 0 or min(width, height) <= 0 or x + width > frame.shape[1] or y + height > frame.shape[0]:
        raise VideoPayloadError("tile is outside source frame")
    region = (x, y, width, height)
    parts = [_slice(plane, layout, *region)
             for plane, layout in zip(frame.planes, frame.plane_layouts)]
    meta = {"pixel_format": frame.pixel_format, "source_shape": list(frame.shape),
            "color_metadata": dict(frame.color_metadata), "region": [x, y, width, height],
            "base_state_hash": base_state_hash,
            "new_state_hash": new_state_hash or canonical_tile_hash(frame, region),
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
        region = (x, y, width, height)
        expected_base = meta.get("base_state_hash")
        if expected_base is not None and canonical_tile_hash(self.frame, region) != expected_base:
            raise VideoPayloadError("tile update base state hash mismatch")
        planes = [plane.copy() for plane in self.frame.planes]
        for index, (descriptor, compressed) in enumerate(zip(meta["planes"], blobs)):
            shape = tuple(int(value) for value in descriptor["shape"])
            dtype = np.dtype(descriptor["dtype"])
            if len(shape) != 2 or any(value <= 0 for value in shape):
                raise VideoPayloadError("invalid tile plane shape")
            expected = int(np.prod(shape, dtype=np.int64)) * dtype.itemsize
            if dtype.kind != "u" or dtype.itemsize not in (1, 2) or expected != int(descriptor["raw_length"]):
                raise VideoPayloadError("invalid tile plane layout")
            raw = _decompress_exact(compressed, expected)
            tile = np.frombuffer(raw, dtype=dtype).reshape(shape)
            target = planes[index]
            layout = self.frame.plane_layouts[index]
            x0, y0, x1, y1 = _bounds(layout, x, y, width, height)
            view = target[y0:min(y1, target.shape[0]), x0:min(x1, target.shape[1])]
            if tile.shape != view.shape:
                raise VideoPayloadError("tile plane shape mismatch")
            view[:] = tile
        self.frame = canonical_frame(tuple(planes), pixel_format=self.frame.pixel_format,
                                     source_shape=self.frame.shape,
                                     color_metadata=dict(self.frame.color_metadata))
        expected_new = meta.get("new_state_hash")
        if not isinstance(expected_new, str) or canonical_tile_hash(self.frame, region) != expected_new:
            raise VideoPayloadError("tile update new state hash mismatch")
        return self.frame
