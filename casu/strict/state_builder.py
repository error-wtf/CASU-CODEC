from __future__ import annotations

from collections.abc import Iterable, Iterator

from .model import RationalTime, StrictFrame
from .tiles import compare_frames


def iter_state_map(frames: Iterable[StrictFrame], *, tile_width: int = 64,
                   tile_height: int = 64) -> Iterator[dict]:
    iterator = iter(frames)
    try:
        current = next(iterator)
    except StopIteration:
        return
    previous: StrictFrame | None = None
    while True:
        try:
            following = next(iterator)
        except StopIteration:
            following = None
        if previous is not None and current.time.fraction < previous.time.fraction:
            raise ValueError("source PTS must be monotonic in presentation order")
        if following is not None and following.time.fraction < current.time.fraction:
            raise ValueError("source PTS must be monotonic in presentation order")
        valid_until = following.time if following else (
            RationalTime(current.pts + current.duration_pts,
                         current.time_base_num, current.time_base_den)
            if current.duration_pts is not None and current.duration_pts > 0 else None
        )
        for item in compare_frames(
            previous.frame if previous else None,
            current.frame,
            valid_from=current.time,
            valid_until=valid_until,
            tile_width=tile_width,
            tile_height=tile_height,
        ):
            yield item.as_dict()
        if following is None:
            break
        previous, current = current, following


def build_state_map(frames: Iterable[StrictFrame], *, tile_width: int = 64,
                    tile_height: int = 64) -> list[dict]:
    return list(iter_state_map(frames, tile_width=tile_width, tile_height=tile_height))
