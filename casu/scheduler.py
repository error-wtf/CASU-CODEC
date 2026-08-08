# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Deterministic CASU state scheduler for validated sidecar manifests.

This layer deliberately schedules *metadata states* only. It never invents a
frame, changes source timestamps, or replaces the media decoder.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class SegmentState:
    start_s: float
    end_s: float
    state: str
    source: str


class CasuScheduler:
    def __init__(self, segments: Iterable[SegmentState]):
        self._segments = tuple(sorted(segments, key=lambda item: (item.start_s, item.end_s)))

    @classmethod
    def from_manifest(cls, manifest: dict[str, Any], source: str = "video") -> "CasuScheduler":
        section = manifest.get(source) or {}
        raw = section.get("segments", []) if isinstance(section, dict) else []
        parsed: list[SegmentState] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                parsed.append(SegmentState(float(item["start_s"]), float(item["end_s"]), str(item["state"]), source))
            except (KeyError, TypeError, ValueError):
                continue
        return cls(parsed)

    def state_at(self, timestamp_s: float) -> SegmentState | None:
        """Return the state active at a source timestamp, if covered."""
        value = float(timestamp_s)
        for segment in self._segments:
            if segment.start_s <= value < segment.end_s:
                return segment
        return None

    def summary(self, timestamp_s: float) -> dict[str, Any]:
        active = self.state_at(timestamp_s)
        return {
            "source": self._segments[0].source if self._segments else "unknown",
            "segment_count": len(self._segments),
            "active_state": active.state if active else None,
            "active_interval": [active.start_s, active.end_s] if active else None,
            "covered": active is not None,
        }
