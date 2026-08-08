"""Reference type skeletons for CASU strict/native work.

This file is guidance. Integrate into the repository architecture instead of
blindly importing it as a new duplicate model layer.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class RationalTime:
    pts: int
    time_base_num: int
    time_base_den: int

    def seconds(self) -> float:
        return self.pts * self.time_base_num / self.time_base_den

@dataclass(frozen=True)
class CanonicalPlane:
    index: int
    width: int
    height: int
    bit_depth: int
    bytes_per_sample: int
    subsample_x: int
    subsample_y: int
    data: bytes

@dataclass(frozen=True)
class CanonicalVideoFrame:
    time: RationalTime
    duration_pts: int | None
    width: int
    height: int
    pixel_format: str
    color_range: str | None
    color_primaries: str | None
    color_transfer: str | None
    color_space: str | None
    chroma_location: str | None
    planes: tuple[CanonicalPlane, ...]

@dataclass(frozen=True)
class TileState:
    tile_id: str
    x: int
    y: int
    width: int
    height: int
    valid_from: RationalTime
    valid_until_pts: int | None
    lifecycle: Literal["CREATE", "UPDATE", "HOLD", "INVALIDATE", "RELEASE"]
    base_state_hash: str | None
    state_hash: str
