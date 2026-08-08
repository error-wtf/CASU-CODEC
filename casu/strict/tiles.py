from __future__ import annotations

from .canonical import CanonicalFrame
from .model import StrictTileState


def _regions(shape: tuple[int, int], tile_width: int, tile_height: int):
    height, width = shape
    ordinal = 0
    for y in range(0, height, tile_height):
        for x in range(0, width, tile_width):
            yield (f"tile-{ordinal:08d}", x, y, min(tile_width, width - x), min(tile_height, height - y))
            ordinal += 1


def compare_frames(previous: CanonicalFrame | None, current: CanonicalFrame, *,
                   timestamp_s: float, next_timestamp_s: float | None = None,
                   tile_width: int = 64, tile_height: int = 64) -> list[StrictTileState]:
    if tile_width <= 0 or tile_height <= 0:
        raise ValueError("tile dimensions must be positive")
    if previous is not None and previous.shape != current.shape:
        raise ValueError("source resolution changes require a new stream state")
    result: list[StrictTileState] = []
    for tile_id, x, y, width, height in _regions(current.shape, tile_width, tile_height):
        current_parts = tuple(_plane_tile(plane, x, y, width, height, current.shape[1], current.shape[0])
                              for plane in current.planes)
        previous_parts = (tuple(_plane_tile(plane, x, y, width, height, previous.shape[1], previous.shape[0])
                                for plane in previous.planes)
                         if previous is not None else None)
        current_hash = _digest_parts(current_parts)
        reference_hash = _digest_parts(previous_parts) if previous_parts is not None else None
        identical = (reference_hash is not None and current_hash == reference_hash
                     and previous.pixel_format == current.pixel_format
                     and previous.color_metadata == current.color_metadata
                     and previous.shape == current.shape)
        result.append(StrictTileState(tile_id, {"x": x, "y": y, "w": width, "h": height},
                                     "HOLD" if identical else "UPDATE", float(timestamp_s),
                                     next_timestamp_s, current_hash, reference_hash,
                                     len(current.planes)))
    return result


def _digest_parts(parts) -> str:
    import hashlib
    digest = hashlib.sha256()
    for plane in parts:
        digest.update(str(plane.shape).encode("ascii"))
        digest.update(str(plane.dtype).encode("ascii"))
        digest.update(plane.tobytes(order="C"))
    return digest.hexdigest()


def _plane_tile(plane, x: int, y: int, width: int, height: int,
                source_width: int, source_height: int):
    """Map a source-resolution tile onto a possibly subsampled plane."""
    plane_h, plane_w = plane.shape[:2]
    x0 = (x * plane_w) // source_width
    y0 = (y * plane_h) // source_height
    x1 = max(x0 + 1, ((x + width) * plane_w + source_width - 1) // source_width)
    y1 = max(y0 + 1, ((y + height) * plane_h + source_height - 1) // source_height)
    return plane[y0:min(y1, plane_h), x0:min(x1, plane_w)]
