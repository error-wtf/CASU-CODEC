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
                  width: int = 160, height: int = 90) -> dict[str, Any]:
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
    while True:
        raw = process.stdout.read(size)
        if len(raw) != size:
            break
        frame = np.frombuffer(raw, dtype=np.uint8).astype(np.int16)
        delta = 1.0 if previous is None else float(np.abs(frame - previous).mean() / 255.0)
        state = "motion" if delta >= 0.010 else "low_motion" if delta >= 0.0015 else "static"
        deltas.append(delta)
        states.append(state)
        previous = frame
    error = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
    if process.wait() != 0:
        raise CasuError(f"video analysis failed: {error.strip()}")
    total = max(1, len(states))
    counts = {name: states.count(name) for name in ("static", "low_motion", "motion")}
    return {
        "method": "decoded grayscale temporal activity hint",
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
        "segments": rle(states, 1.0 / analysis_fps, duration(probe)),
        "state_is_hint_only": True,
    }


def analyze_audio(path: Path, probe: dict[str, Any], sample_rate: int = 16000,
                  window_ms: int = 20) -> dict[str, Any]:
    audio = stream(probe, "audio")
    if not audio:
        return {}
    command = ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-vn",
               "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "pipe:1"]
    try:
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as exc:
        raise CasuError(f"audio analysis failed: {exc.stderr.decode(errors='replace').strip()}") from exc
    samples = np.frombuffer(result.stdout, dtype=np.float32)
    window = max(1, int(sample_rate * window_ms / 1000))
    count = (len(samples) + window - 1) // window
    if not count:
        return {"source_codec": audio.get("codec_name"), "segments": []}
    padded = np.zeros(count * window, dtype=np.float32)
    padded[:len(samples)] = samples
    samples = padded.reshape(count, window)
    db = 20.0 * np.log10(np.sqrt(np.mean(samples * samples, axis=1) + 1e-12) + 1e-12)
    states = np.where(db < -55.0, "silence", np.where(db < -38.0, "low_level", "active")).tolist()
    counts = {name: states.count(name) for name in ("silence", "low_level", "active")}
    total = max(1, len(states))
    return {
        "method": "decoded PCM RMS activity hint",
        "source_codec": audio.get("codec_name"),
        "sample_rate": sample_rate,
        "window_ms": window_ms,
        "sample_windows": count,
        "activity_ratio": {key: round(value / total, 6) for key, value in counts.items()},
        "mean_dbfs": round(float(np.mean(db)), 3),
        "segments": rle(states, window_ms / 1000, duration(probe)),
        "state_is_hint_only": True,
    }


def analyze(path: Path, analysis_fps: float = 10.0, mode: str = "strict") -> dict[str, Any]:
    if mode not in ANALYSIS_MODES:
        raise CasuError(f"unknown analysis mode: {mode}; choose one of {sorted(ANALYSIS_MODES)}")
    path = path.expanduser().resolve()
    if not path.is_file():
        raise CasuError(f"input not found: {path}")
    if path.suffix.lower() == ".casu":
        raise CasuError("input is already a CASU manifest; convert the original MP4/MP3 media instead")
    probe = ffprobe(path)
    fmt = probe.get("format", {})
    stat = path.stat()
    digest = sha256_file(path)
    return {
        "format": {"magic": "MPCASU\\0", "kind": "CASU sidecar manifest", "schema": "0.2"},
        "casu": {"name": "CASU", "acronym": "Codec for All Segmented Units", "short_name": "CASU", "container_extension": ".casu", "version": __version__, "analysis_mode": mode,
                        "compatibility": "legacy media remains canonical; sidecar is optional"},
        "source": {"filename": path.name, "path": str(path), "size_bytes": stat.st_size,
                   "sha256": digest,
                   "format_name": fmt.get("format_name"), "duration_s": duration(probe)},
        "streams": [{key: item.get(key) for key in ("index", "codec_type", "codec_name", "width", "height", "sample_rate", "channels", "time_base")}
                    for item in probe.get("streams", [])],
        "video": analyze_video(path, probe, analysis_fps=analysis_fps),
        "audio": analyze_audio(path, probe),
        "integrity": {"timestamps_are_source_of_truth": True, "optimization_is_hint_only": True, "mode_is_not_quality_proof": True,
                      "fallback": "full-frame/full-fidelity legacy playback"},
    }


def play(path: Path, extra: list[str] | None = None) -> None:
    require_tool("ffplay")
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
    run(["ffplay", "-autoexit", "-hide_banner", *(extra or []), str(path)])
