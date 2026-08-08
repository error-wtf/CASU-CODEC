from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .canonical import CanonicalFrame


@dataclass(frozen=True)
class StrictFrame:
    pts: int
    time_base_num: int
    time_base_den: int
    frame: CanonicalFrame

    @property
    def timestamp_s(self) -> float:
        if self.time_base_den <= 0:
            raise ValueError("time base denominator must be positive")
        return self.pts * self.time_base_num / self.time_base_den


@dataclass(frozen=True)
class StrictTileState:
    tile_id: str
    region: dict[str, int]
    state: str
    valid_from_s: float
    valid_until_s: float | None
    state_hash: str
    reference_hash: str | None
    plane_count: int

    def as_dict(self) -> dict[str, Any]:
        return {"tile_id": self.tile_id, "region": self.region, "state": self.state,
                "valid_from_s": self.valid_from_s, "valid_until_s": self.valid_until_s,
                "state_hash": self.state_hash, "reference_hash": self.reference_hash,
                "plane_count": self.plane_count, "fidelity": "SOURCE_RESOLUTION_STRICT"}
