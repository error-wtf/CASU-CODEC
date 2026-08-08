# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
from __future__ import annotations

import json
import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from . import __version__


class CasuError(RuntimeError):
    pass


ANALYSIS_MODES = frozenset({"strict", "visually_lossless", "adaptive"})


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_casu_source(path: Path) -> Path:
    """Resolve a CASU manifest to its original media without changing it."""
    path = path.expanduser().resolve()
    if path.suffix.lower() != ".casu":
        return path
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        source = Path(manifest["source"]["path"]).expanduser()
        if source.is_file():
            candidate = source.resolve()
        else:
            candidate = path.parent / manifest["source"]["filename"]
            if not candidate.is_file():
                raise CasuError(f"CASU source media not found: {path}")
            candidate = candidate.resolve()
        expected_size = manifest.get("source", {}).get("size_bytes")
        if expected_size is not None:
            try:
                if candidate.stat().st_size != int(expected_size):
                    raise CasuError(f"CASU source size mismatch: {candidate}")
            except (TypeError, ValueError):
                raise CasuError(f"CASU source size is invalid: {path}")
        expected = manifest.get("source", {}).get("sha256")
        if expected and sha256_file(candidate) != expected:
            raise CasuError(f"CASU source integrity mismatch: {candidate}")
        return candidate
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        pass
    raise CasuError(f"CASU source media not found: {path}")


def require_tool(name: str) -> str:
    value = shutil.which(name)
    if not value:
        raise CasuError(f"required tool not found: {name}")
    return value


def run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command, check=True, text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip() if capture else str(exc)
        raise CasuError(detail) from exc


def ffprobe(path: Path) -> dict[str, Any]:
    require_tool("ffprobe")
    result = run([
        "ffprobe", "-v", "error", "-show_streams", "-show_format",
        "-of", "json", str(path),
    ], capture=True)
    return json.loads(result.stdout)


def stream(probe: dict[str, Any], kind: str) -> dict[str, Any] | None:
    return next((item for item in probe.get("streams", []) if item.get("codec_type") == kind), None)


def duration(probe: dict[str, Any]) -> float:
    try:
        return float(probe.get("format", {}).get("duration") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def rle(states: list[str], step: float, end_s: float | None = None) -> list[dict[str, Any]]:
    if not states:
        return []
    result: list[dict[str, Any]] = []
    start, current = 0, states[0]
    for index, state in enumerate(states[1:], 1):
        if state != current:
            result.append(_interval(start, index, current, step))
            start, current = index, state
    result.append(_interval(start, len(states), current, step))
    if end_s is not None and result:
        result[-1]["end_s"] = round(min(result[-1]["end_s"], end_s), 6)
        result[-1]["duration_s"] = round(max(0.0, result[-1]["end_s"] - result[-1]["start_s"]), 6)
        result[-1]["valid_until_s"] = result[-1]["end_s"]
        result[-1]["deadline_s"] = result[-1]["end_s"]
    return result


def _interval(start: int, end: int, state: str, step: float) -> dict[str, Any]:
    start_s = round(start * step, 6)
    end_s = round(end * step, 6)
    return {
        "start_s": start_s,
        "end_s": end_s,
        "duration_s": round(end_s - start_s, 6),
        "state": state,
        "valid_until_s": end_s,
        "deadline_s": end_s,
        "priority": 0,
        "change_type": "state_change" if start else "initial_state",
    }


def analyze_video(path: Path, probe: dict[str, Any], analysis_fps: float = 10.0,
                  width: int = 160, height: int = 90, mode: str = "strict") -> dict[str, Any]:
    if not np.isfinite(analysis_fps) or analysis_fps <= 0:
        raise CasuError("analysis FPS must be finite and positive")
    if width <= 0 or height <= 0:
        raise CasuError("analysis dimensions must be positive")
    if mode not in ANALYSIS_MODES:
        raise CasuError(f"unknown video analysis mode: {mode}")
    video = stream(probe, "video")
    if not video:
        return {}
    command = [
        "ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", "-an",
        "-vf", f"fps={analysis_fps},scale={width}:{height}:flags=area,format=gray",
        "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.stdout is None:
        raise CasuError("could not open FFmpeg video output")
    size = width * height
    previous = None
    deltas: list[float] = []
    states: list[str] = []
    tile_changes: list[float] = []
    tile_width = max(1, min(16, width // 8))
    tile_height = max(1, min(16, height // 8))
    while True:
        raw = process.stdout.read(size)
        if len(raw) != size:
            break
        frame = np.frombuffer(raw, dtype=np.uint8).astype(np.int16)
        delta = 1.0 if previous is None else float(np.abs(frame - previous).mean() / 255.0)
        if previous is None:
            changed_ratio = 1.0
        else:
            current_grid = frame.reshape(height, width)
            previous_grid = previous.reshape(height, width)
            changed = 0
            total = 0
            for y in range(0, height, tile_height):
                for x in range(0, width, tile_width):
                    tile_delta = np.abs(current_grid[y:y + tile_height, x:x + tile_width] - previous_grid[y:y + tile_height, x:x + tile_width]).mean() / 255.0
                    # These thresholds define analysis hints only. They do
                    # not establish strict pixel identity on downscaled
                    # grayscale frames.
                    threshold = {"strict": 0.01, "visually_lossless": 0.03, "adaptive": 0.08}[mode]
                    changed += int(tile_delta > threshold)
                    total += 1
            changed_ratio = changed / max(1, total)
        state = "motion" if delta >= 0.010 else "low_motion" if delta >= 0.0015 else "static"
        deltas.append(delta)
        tile_changes.append(changed_ratio)
        states.append(state)
        previous = frame
    error = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
    if process.wait() != 0:
        raise CasuError(f"video analysis failed: {error.strip()}")
    total = max(1, len(states))
    counts = {name: states.count(name) for name in ("static", "low_motion", "motion")}
    return {
        "method": "decoded grayscale temporal activity hint",
        "analysis_mode": mode,
        "analysis_fps": analysis_fps,
        "analysis_resolution": [width, height],
        "source_width": video.get("width"),
        "source_height": video.get("height"),
        "source_codec": video.get("codec_name"),
        "source_time_base": video.get("time_base"),
        "sample_count": len(states),
        "activity_ratio": {key: round(value / total, 6) for key, value in counts.items()},
        "mean_frame_delta": round(float(np.mean(deltas)) if deltas else 0.0, 8),
        "p95_frame_delta": round(float(np.percentile(deltas, 95)) if deltas else 0.0, 8),
        "spatial_analysis": {
            "method": "decoded grayscale tile change ratio",
            "tile_size": [tile_width, tile_height],
            "tile_grid": [int(np.ceil(width / tile_width)), int(np.ceil(height / tile_height))],
            "mean_changed_tile_ratio": round(float(np.mean(tile_changes)) if tile_changes else 0.0, 8),
            "p95_changed_tile_ratio": round(float(np.percentile(tile_changes, 95)) if tile_changes else 0.0, 8),
            "strict_pixel_identical_available": False,
            "strict_pixel_identity_note": "requires canonical-resolution pixel/plane tile comparison; this reduced preview is not an identity proof",
            "mode_threshold": {"strict": 0.01, "visually_lossless": 0.03, "adaptive": 0.08}[mode],
            "state_is_hint_only": True,
        },
        "segments": rle(states, 1.0 / analysis_fps, duration(probe)),
        "state_is_hint_only": True,
    }


def analyze_audio(path: Path, probe: dict[str, Any], sample_rate: int = 16000,
                  window_ms: int = 20) -> dict[str, Any]:
    if sample_rate <= 0 or window_ms <= 0:
        raise CasuError("audio sample rate and window must be positive")
    audio = stream(probe, "audio")
    if not audio:
        return {}
    command = ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-vn",
               "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "pipe:1"]
    window = max(1, int(sample_rate * window_ms / 1000))
    window_bytes = window * np.dtype(np.float32).itemsize
    states: list[str] = []
    db_values: list[float] = []
    pending = bytearray()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.stdout is None:
        raise CasuError("could not open FFmpeg audio output")
    while True:
        chunk = process.stdout.read(max(window_bytes, 64 * 1024))
        if not chunk:
            break
        pending.extend(chunk)
        complete = (len(pending) // window_bytes) * window_bytes
        if not complete:
            continue
        raw = bytes(pending[:complete])
        del pending[:complete]
        samples = np.frombuffer(raw, dtype=np.float32).reshape(-1, window)
        db = 20.0 * np.log10(np.sqrt(np.mean(samples * samples, axis=1) + 1e-12) + 1e-12)
        db_values.extend(float(value) for value in db)
        states.extend(np.where(db < -55.0, "silence", np.where(db < -38.0, "low_level", "active")).tolist())
    if pending:
        tail = np.frombuffer(bytes(pending), dtype=np.float32)
        if tail.size:
            padded = np.zeros(window, dtype=np.float32)
            padded[:tail.size] = tail
            value = float(20.0 * np.log10(np.sqrt(np.mean(padded * padded) + 1e-12) + 1e-12))
            db_values.append(value)
            states.append("silence" if value < -55.0 else "low_level" if value < -38.0 else "active")
    error = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
    if process.wait() != 0:
        raise CasuError(f"audio analysis failed: {error.strip()}")
    count = len(states)
    if not count:
        return {"source_codec": audio.get("codec_name"), "segments": []}
    counts = {name: states.count(name) for name in ("silence", "low_level", "active")}
    total = max(1, len(states))
    return {
        "method": "decoded PCM RMS activity hint",
        "source_codec": audio.get("codec_name"),
        "sample_rate": sample_rate,
        "window_ms": window_ms,
        "sample_windows": count,
        "activity_ratio": {key: round(value / total, 6) for key, value in counts.items()},
        "mean_dbfs": round(float(np.mean(db_values)), 3),
        "segments": rle(states, window_ms / 1000, duration(probe)),
        "state_is_hint_only": True,
    }


def analyze(path: Path, analysis_fps: float = 10.0, mode: str = "strict") -> dict[str, Any]:
    if mode not in ANALYSIS_MODES:
        raise CasuError(f"unknown analysis mode: {mode}; choose one of {sorted(ANALYSIS_MODES)}")
    if not np.isfinite(analysis_fps) or analysis_fps <= 0:
        raise CasuError("analysis FPS must be finite and positive")
    path = path.expanduser().resolve()
    if not path.is_file():
        raise CasuError(f"input not found: {path}")
    if path.suffix.lower() == ".casu":
        raise CasuError("input is already a CASU manifest; convert the original MP4/MP3 media instead")
    probe = ffprobe(path)
    fmt = probe.get("format", {})
    stat = path.stat()
    digest = sha256_file(path)
    manifest = {
        "format": {"magic": "MPCASU\\0", "kind": "CASU sidecar manifest", "schema": "0.2"},
        "casu": {"name": "CASU", "acronym": "Codec for All Segmented Units", "short_name": "CASU", "container_extension": ".casu", "version": __version__, "analysis_mode": mode,
                        "compatibility": "legacy media remains canonical; sidecar is optional"},
        "source": {"filename": path.name, "path": str(path), "size_bytes": stat.st_size,
                   "sha256": digest,
                   "format_name": fmt.get("format_name"), "duration_s": duration(probe)},
        "streams": [{key: item.get(key) for key in ("index", "codec_type", "codec_name", "width", "height", "sample_rate", "channels", "time_base")}
                    for item in probe.get("streams", [])],
        "video": analyze_video(path, probe, analysis_fps=analysis_fps, mode=mode),
        "audio": analyze_audio(path, probe),
        "integrity": {"timestamps_are_source_of_truth": True, "optimization_is_hint_only": True, "mode_is_not_quality_proof": True,
                      "fallback": "full-frame/full-fidelity legacy playback"},
    }
    # Keep the public API fail-closed: a converter must never emit a manifest
    # that its own validator would reject.
    from .schema import validate_manifest
    errors = validate_manifest(manifest)
    if errors:
        raise CasuError("internal manifest validation failed: " + errors[0])
    return manifest


def play(path: Path, extra: list[str] | None = None) -> None:
    """Reject the legacy CLI player path; MPCASU owns playback in-process."""
    path = path.expanduser().resolve()
    if not path.is_file():
        raise CasuError(f"media not found: {path}")
    if path.suffix.lower() == ".casu":
        try:
            from .schema import validate_manifest
            manifest = json.loads(path.read_text(encoding="utf-8"))
            errors = validate_manifest(manifest)
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise CasuError(f"invalid CASU manifest: {path}") from exc
        if errors:
            raise CasuError(f"invalid CASU manifest: {errors[0]}")
        path = resolve_casu_source(path)
    raise CasuError("external playback is not supported; use the MPCASU in-process player")
