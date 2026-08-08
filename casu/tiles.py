# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Deterministic spatial state primitives for CASU.

This module intentionally contains no decoder or renderer.  It operates on
already decoded canonical image planes and makes the distinction between an
exact HOLD and an analysis hint explicit.  A reduced preview must never be
presented as proof of pixel identity.
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

import numpy as np


class TileStateError(ValueError):
    """Raised when decoded frames cannot be compared safely."""


@dataclass(frozen=True)
class TileRegion:
    tile_id: str
    x: int
    y: int
    width: int
    height: int

    def as_dict(self) -> dict[str, Any]:
        return {"tile_id": self.tile_id, "x": self.x, "y": self.y,
                "w": self.width, "h": self.height}


def canonical_frame(frame: np.ndarray) -> np.ndarray:
    """Return a contiguous uint8 frame with a stable byte representation."""
    value = np.asarray(frame)
    if value.ndim not in (2, 3) or value.size == 0:
        raise TileStateError("decoded frame must be a non-empty 2D or 3D array")
    if value.dtype != np.uint8:
        raise TileStateError("decoded frame must use canonical uint8 samples")
    return np.ascontiguousarray(value)


def tile_regions(shape: tuple[int, ...], tile_width: int = 64,
                 tile_height: int = 64) -> Iterator[TileRegion]:
    """Yield deterministic row-major regions for a decoded frame shape."""
    if len(shape) < 2:
        raise TileStateError("frame shape must contain height and width")
    height, width = int(shape[0]), int(shape[1])
    if width <= 0 or height <= 0 or tile_width <= 0 or tile_height <= 0:
        raise TileStateError("frame and tile dimensions must be positive")
    ordinal = 0
    for y in range(0, height, tile_height):
        for x in range(0, width, tile_width):
            yield TileRegion(f"tile-{ordinal:08d}", x, y,
                             min(tile_width, width - x),
                             min(tile_height, height - y))
            ordinal += 1


def _tile(frame: np.ndarray, region: TileRegion) -> np.ndarray:
    return frame[region.y:region.y + region.height,
                 region.x:region.x + region.width, ...]


def tile_digest(frame: np.ndarray, region: TileRegion) -> str:
    """Hash the exact canonical bytes of one tile."""
    value = canonical_frame(frame)
    tile = np.ascontiguousarray(_tile(value, region))
    digest = hashlib.sha256()
    digest.update(str(tile.shape).encode("ascii"))
    digest.update(tile.tobytes(order="C"))
    return digest.hexdigest()


def compare_tile_frames(previous: np.ndarray | None, current: np.ndarray,
                        *, tile_width: int = 64, tile_height: int = 64,
                        mode: str = "strict", threshold: float | None = None,
                        timestamp_s: float = 0.0,
                        next_timestamp_s: float | None = None) -> list[dict[str, Any]]:
    """Create per-tile state records for two canonical decoded frames.

    In ``strict`` mode HOLD is emitted only when the complete tile byte payload
    is identical.  Other modes are explicitly hints and use a bounded mean
    absolute difference threshold; they never claim pixel identity.
    """
    if mode not in {"strict", "visually_lossless", "adaptive"}:
        raise TileStateError(f"unsupported tile comparison mode: {mode}")
    current_value = canonical_frame(current)
    previous_value = canonical_frame(previous) if previous is not None else None
    if previous_value is not None and previous_value.shape != current_value.shape:
        raise TileStateError("adjacent frames must have identical canonical shapes")
    if threshold is None:
        threshold = {"strict": 0.0, "visually_lossless": 0.01,
                     "adaptive": 0.05}[mode]
    if threshold < 0 or threshold > 1:
        raise TileStateError("tile threshold must be between zero and one")
    result: list[dict[str, Any]] = []
    for region in tile_regions(current_value.shape, tile_width, tile_height):
        current_tile = _tile(current_value, region)
        current_hash = tile_digest(current_value, region)
        previous_hash = tile_digest(previous_value, region) if previous_value is not None else None
        if previous_value is None:
            state, lifecycle = "UPDATE", "CREATE"
            difference = 1.0
        elif mode == "strict":
            identical = previous_hash == current_hash
            state, lifecycle = ("HOLD", "HOLD") if identical else ("UPDATE", "UPDATE")
            difference = 0.0 if identical else 1.0
        else:
            previous_tile = _tile(previous_value, region).astype(np.int16)
            difference = float(np.abs(current_tile.astype(np.int16) - previous_tile).mean() / 255.0)
            identical = difference <= threshold
            state, lifecycle = ("HOLD", "HOLD") if identical else ("UPDATE", "UPDATE")
        record = {
            "segment_id": f"{region.tile_id}@{timestamp_s:.6f}",
            "tile_id": region.tile_id,
            "region": region.as_dict(),
            "valid_from_s": float(timestamp_s),
            "valid_until_s": None if next_timestamp_s is None else float(next_timestamp_s),
            "state": state,
            "lifecycle": lifecycle,
            "base_state_hash": previous_hash,
            "state_hash": current_hash,
            "difference_ratio": round(difference, 8),
            "fidelity_class": "LOSSLESS_REALTIME" if mode == "strict" else mode.upper(),
        }
        result.append(record)
    return result


def state_map_from_frames(frames: Iterable[tuple[float, np.ndarray]], *,
                          tile_width: int = 64, tile_height: int = 64,
                          mode: str = "strict") -> list[dict[str, Any]]:
    """Build a deterministic append-only per-tile ``S(x,y,t)`` state map."""
    iterator = iter(frames)
    try:
        timestamp, frame = next(iterator)
    except StopIteration:
        return []
    previous = None
    output: list[dict[str, Any]] = []
    for next_timestamp, next_frame in iterator:
        output.extend(compare_tile_frames(previous, frame,
                                          tile_width=tile_width,
                                          tile_height=tile_height,
                                          mode=mode,
                                          timestamp_s=float(timestamp),
                                          next_timestamp_s=float(next_timestamp)))
        previous, timestamp, frame = frame, next_timestamp, next_frame
    output.extend(compare_tile_frames(previous, frame,
                                      tile_width=tile_width,
                                      tile_height=tile_height,
                                      mode=mode,
                                      timestamp_s=float(timestamp)))
    return output
