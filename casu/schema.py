from __future__ import annotations

import math
import re
from typing import Any


class CasuManifestError(ValueError):
    pass


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    """Return all structural problems without changing the source media."""
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest must be an object"]
    identity = manifest.get("casu") or {}
    format_info = manifest.get("format") or {}
    if format_info and format_info.get("magic") not in (None, "MPCASU\\0"):
        errors.append("format.magic must be MPCASU\\0 when present")
    if identity.get("name") != "CASU":
        errors.append("casu.name must be CASU")
    if identity.get("container_extension") != ".casu":
        errors.append("casu.container_extension must be .casu")
    source = manifest.get("source") or {}
    if not isinstance(source.get("filename"), str) or not source.get("filename"):
        errors.append("source.filename must be a non-empty string")
    if "duration_s" not in source:
        errors.append("source.duration_s is required")
    try:
        duration = float(source.get("duration_s") or 0)
    except (TypeError, ValueError):
        errors.append("source.duration_s must be numeric")
        duration = 0.0
    if not math.isfinite(duration) or duration < 0:
        errors.append("source.duration_s must be finite and non-negative")
    if source.get("size_bytes") is not None:
        try:
            size_bytes = float(source.get("size_bytes") or 0)
            if not math.isfinite(size_bytes) or size_bytes < 0:
                errors.append("source.size_bytes must be finite and non-negative")
        except (TypeError, ValueError):
            errors.append("source.size_bytes must be numeric")
    if source.get("sha256") is not None and (
        not isinstance(source.get("sha256"), str)
        or re.fullmatch(r"[0-9a-fA-F]{64}", source["sha256"]) is None
    ):
        errors.append("source.sha256 must be a 64-character hex digest when present")
    for media_key in ("video", "audio"):
        section = manifest.get(media_key) or {}
        if not isinstance(section, dict):
            errors.append(f"{media_key} must be an object")
            continue
        segments = section.get("segments", [])
        if not isinstance(segments, list):
            errors.append(f"{media_key}.segments must be an array")
            continue
        previous_end = 0.0
        for index, segment in enumerate(segments):
            if not isinstance(segment, dict):
                errors.append(f"{media_key}.segments[{index}] must be an object")
                continue
            try:
                start, end = float(segment["start_s"]), float(segment["end_s"])
            except (KeyError, TypeError, ValueError):
                errors.append(f"{media_key}.segments[{index}] lacks numeric start/end")
                continue
            if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start or end > duration + 0.5:
                errors.append(f"{media_key}.segments[{index}] is outside source duration")
            if start < previous_end - 1e-6:
                errors.append(f"{media_key}.segments[{index}] overlaps the preceding segment")
            previous_end = max(previous_end, end)
            if not segment.get("state"):
                errors.append(f"{media_key}.segments[{index}] lacks state")
    integrity = manifest.get("integrity") or {}
    if integrity.get("timestamps_are_source_of_truth") is not True:
        errors.append("integrity.timestamps_are_source_of_truth must be true")
    return errors
