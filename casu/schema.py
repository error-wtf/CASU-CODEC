from __future__ import annotations

from typing import Any


class CasuManifestError(ValueError):
    pass


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    """Return all structural problems without changing the source media."""
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest must be an object"]
    identity = manifest.get("casu") or {}
    if identity.get("name") != "CASU":
        errors.append("casu.name must be CASU")
    if identity.get("container_extension") != ".casu":
        errors.append("casu.container_extension must be .casu")
    source = manifest.get("source") or {}
    for key in ("filename", "duration_s"):
        if key not in source:
            errors.append(f"source.{key} is required")
    duration = float(source.get("duration_s") or 0)
    for media_key in ("video", "audio"):
        section = manifest.get(media_key) or {}
        for index, segment in enumerate(section.get("segments", [])):
            try:
                start, end = float(segment["start_s"]), float(segment["end_s"])
            except (KeyError, TypeError, ValueError):
                errors.append(f"{media_key}.segments[{index}] lacks numeric start/end")
                continue
            if start < 0 or end < start or end > duration + 0.5:
                errors.append(f"{media_key}.segments[{index}] is outside source duration")
            if not segment.get("state"):
                errors.append(f"{media_key}.segments[{index}] lacks state")
    integrity = manifest.get("integrity") or {}
    if integrity.get("timestamps_are_source_of_truth") is not True:
        errors.append("integrity.timestamps_are_source_of_truth must be true")
    return errors

