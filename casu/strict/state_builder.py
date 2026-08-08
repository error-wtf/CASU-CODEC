from __future__ import annotations

from collections.abc import Iterable

from .model import StrictFrame
from .tiles import compare_frames


def build_state_map(frames: Iterable[StrictFrame], *, tile_width: int = 64,
                    tile_height: int = 64) -> list[dict]:
    ordered = list(frames)
    if any(ordered[index].timestamp_s > ordered[index + 1].timestamp_s
           for index in range(len(ordered) - 1)):
        raise ValueError("source PTS must be monotonic")
    output = []
    for index, current in enumerate(ordered):
        previous = ordered[index - 1] if index else None
        next_time = ordered[index + 1].timestamp_s if index + 1 < len(ordered) else None
        output.extend(item.as_dict() for item in compare_frames(
            previous.frame if previous else None, current.frame,
            timestamp_s=current.timestamp_s, next_timestamp_s=next_time,
            tile_width=tile_width, tile_height=tile_height))
    return output
