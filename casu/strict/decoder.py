"""Decoder boundary contract for Gate 2.

The strict state builder accepts frames only when the caller supplies source
PTS/time-base and decoded planes. This module intentionally does not pretend
that an fps-filtered preview provides source timestamps.
"""
from __future__ import annotations

from collections.abc import Iterable

from .model import StrictFrame


def validate_source_frames(frames: Iterable[StrictFrame]) -> list[StrictFrame]:
    values = list(frames)
    for frame in values:
        if frame.time_base_den <= 0:
            raise ValueError("invalid source time base")
        if frame.frame.pixel_format == "gray8":
            # gray8 is allowed only when it is explicitly the source plane;
            # reduced activity previews must not call this API.
            continue
    if any(values[index].timestamp_s > values[index + 1].timestamp_s
           for index in range(len(values) - 1)):
        raise ValueError("source PTS must be monotonic")
    return values
