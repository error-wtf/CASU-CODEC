# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
#!/usr/bin/env python3
"""
SSC v0.1 — Segmented State Codec / compatibility optimizer

Accepts legacy MP4 and MP3 inputs, analyses their temporal structure, writes a
machine-readable segment map, and can create a more efficient legacy-compatible
output without inventing frames or changing playback timing.

Design goals:
- preserve source timing
- identify persistent/static intervals instead of treating every tick equally
- expose temporal hints for future display/audio schedulers
- stay usable today through FFmpeg

This is a research prototype, not a new ISO codec bitstream.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

VERSION = "0.1.0"


class SSCError(RuntimeError):
    pass


def require_tool(name: str) -> str:
    p = shutil.which(name)
    if not p:
        raise SSCError(f"Required tool not found: {name}")
    return p


def run(cmd: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
            text=capture,
        )
    except subprocess.CalledProcessError as e:
        msg = e.stderr.strip() if capture and e.stderr else str(e)
        raise SSCError(msg) from e


def ffprobe(path: Path) -> dict:
    require_tool("ffprobe")
    p = run([
        "ffprobe", "-v", "error",
        "-show_streams", "-show_format",
        "-of", "json", str(path)
    ], capture=True)
    return json.loads(p.stdout)


def stream_of(probe: dict, codec_type: str) -> dict | None:
    for s in probe.get("streams", []):
        if s.get("codec_type") == codec_type:
            return s
    return None


def fraction_to_float(value: str | None, default: float = 0.0) -> float:
    if not value or value in {"0/0", "N/A"}:
        return default
    if "/" in value:
        a, b = value.split("/", 1)
        try:
            return float(a) / float(b)
        except (ValueError, ZeroDivisionError):
            return default
    try:
        return float(value)
    except ValueError:
        return default


def duration_from_probe(probe: dict) -> float:
    try:
        return float(probe.get("format", {}).get("duration", 0.0) or 0.0)
    except ValueError:
        return 0.0


def rle_segments(states: Iterable[str], step_s: float) -> list[dict]:
    states = list(states)
    if not states:
        return []
    out = []
    start = 0
    cur = states[0]
    for i, s in enumerate(states[1:], 1):
        if s != cur:
            out.append({
                "start_s": round(start * step_s, 6),
                "end_s": round(i * step_s, 6),
                "duration_s": round((i - start) * step_s, 6),
                "state": cur,
            })
            start = i
            cur = s
    i = len(states)
    out.append({
        "start_s": round(start * step_s, 6),
        "end_s": round(i * step_s, 6),
        "duration_s": round((i - start) * step_s, 6),
        "state": cur,
    })
    return out


def analyze_video(path: Path, probe: dict, analysis_fps: float = 10.0,
                  width: int = 160, height: int = 90) -> dict:
    vs = stream_of(probe, "video")
    if not vs:
        return {}

    # Low-resolution luma stream is sufficient for temporal activity detection.
    cmd = [
        "ffmpeg", "-v", "error", "-i", str(path),
        "-map", "0:v:0", "-an",
        "-vf", f"fps={analysis_fps},scale={width}:{height}:flags=area,format=gray",
        "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    frame_size = width * height
    prev = None
    diffs: list[float] = []
    states: list[str] = []

    assert proc.stdout is not None
    while True:
        raw = proc.stdout.read(frame_size)
        if len(raw) < frame_size:
            break
        frame = np.frombuffer(raw, dtype=np.uint8).astype(np.int16)
        if prev is None:
            diff = 1.0
            state = "motion"
        else:
            # Mean absolute luma change normalised to [0, 1].
            diff = float(np.mean(np.abs(frame - prev)) / 255.0)
            # Conservative activity classes: these are scheduler hints, not
            # permission to alter source timing.
            if diff < 0.0015:
                state = "static"
            elif diff < 0.010:
                state = "low_motion"
            else:
                state = "motion"
        diffs.append(diff)
        states.append(state)
        prev = frame

    stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
    rc = proc.wait()
    if rc != 0:
        raise SSCError(f"FFmpeg analysis failed: {stderr.strip()}")

    step = 1.0 / analysis_fps
    segments = rle_segments(states, step)
    counts = {k: states.count(k) for k in ("static", "low_motion", "motion")}
    total = max(1, len(states))

    src_fps = fraction_to_float(vs.get("avg_frame_rate"),
                                fraction_to_float(vs.get("r_frame_rate"), 0.0))

    return {
        "analysis_fps": analysis_fps,
        "analysis_resolution": [width, height],
        "source_width": vs.get("width"),
        "source_height": vs.get("height"),
        "source_fps": src_fps,
        "sample_count": len(states),
        "activity_ratio": {
            "static": round(counts["static"] / total, 6),
            "low_motion": round(counts["low_motion"] / total, 6),
            "motion": round(counts["motion"] / total, 6),
        },
        "mean_frame_delta": round(float(np.mean(diffs)) if diffs else 0.0, 8),
        "p95_frame_delta": round(float(np.percentile(diffs, 95)) if diffs else 0.0, 8),
        "segments": segments,
        "scheduler_hints": {
            "static": "hold/persistent state; do not invent refresh work",
            "low_motion": "adaptive update candidate; preserve timestamps",
            "motion": "realtime path; preserve source cadence",
        },
    }


def analyze_audio(path: Path, probe: dict, sample_rate: int = 16000,
                  window_ms: int = 20) -> dict:
    astream = stream_of(probe, "audio")
    if not astream:
        return {}

    cmd = [
        "ffmpeg", "-v", "error", "-i", str(path),
        "-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(sample_rate),
        "-f", "f32le", "pipe:1",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    raw, err = proc.communicate()
    if proc.returncode != 0:
        raise SSCError(f"FFmpeg audio analysis failed: {err.decode(errors='replace').strip()}")

    samples = np.frombuffer(raw, dtype=np.float32)
    win = max(1, int(sample_rate * window_ms / 1000.0))
    n = len(samples) // win
    if n == 0:
        return {"segments": [], "activity_ratio": {}}
    samples = samples[:n * win].reshape(n, win)
    rms = np.sqrt(np.mean(samples * samples, axis=1) + 1e-12)
    db = 20.0 * np.log10(rms + 1e-12)

    states = np.where(db < -55.0, "silence",
             np.where(db < -38.0, "low_level", "active")).tolist()
    step = window_ms / 1000.0
    segments = rle_segments(states, step)
    counts = {k: states.count(k) for k in ("silence", "low_level", "active")}
    total = max(1, len(states))

    return {
        "analysis_sample_rate": sample_rate,
        "window_ms": window_ms,
        "sample_windows": n,
        "activity_ratio": {k: round(v / total, 6) for k, v in counts.items()},
        "mean_dbfs": round(float(np.mean(db)), 3),
        "p95_dbfs": round(float(np.percentile(db, 95)), 3),
        "segments": segments,
        "scheduler_hints": {
            "silence": "decoder/output clock-gating candidate; never shorten timeline",
            "low_level": "normal decode path; optional low-power DSP mode",
            "active": "full fidelity path",
        },
    }


def make_manifest(path: Path, analysis_fps: float = 10.0) -> dict:
    probe = ffprobe(path)
    fmt = probe.get("format", {})
    return {
        "ssc": {
            "name": "Segmented State Codec",
            "version": VERSION,
            "principle": "preserve source timing; encode temporal state and change rather than inventing frames",
        },
        "source": {
            "path": str(path),
            "filename": path.name,
            "size_bytes": path.stat().st_size,
            "format_name": fmt.get("format_name"),
            "duration_s": duration_from_probe(probe),
        },
        "video": analyze_video(path, probe, analysis_fps=analysis_fps),
        "audio": analyze_audio(path, probe),
    }


def write_manifest(manifest: dict, out: Path) -> None:
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def encoder_exists(name: str) -> bool:
    p = run(["ffmpeg", "-hide_banner", "-encoders"], capture=True)
    return name in p.stdout


def optimize_mp4(src: Path, dst: Path, profile: str, collapse_static: bool,
                 crf: int | None = None) -> None:
    # Profiles deliberately separate compatibility from storage efficiency.
    if profile == "compat":
        codec, default_crf, preset = "libx264", 20, "medium"
        extra = ["-pix_fmt", "yuv420p"]
    elif profile == "efficient":
        codec, default_crf, preset = "libx265", 24, "medium"
        extra = ["-tag:v", "hvc1", "-pix_fmt", "yuv420p"]
    elif profile == "max":
        codec, default_crf, preset = "libsvtav1", 30, "6"
        extra = ["-pix_fmt", "yuv420p"]
    else:
        raise SSCError(f"Unknown profile: {profile}")

    if not encoder_exists(codec):
        raise SSCError(f"FFmpeg encoder unavailable: {codec}")

    vf: list[str] = []
    if collapse_static:
        # Conservative duplicate-frame collapse. Timestamps remain VFR; no
        # interpolation and no timeline shortening is performed.
        vf.append("mpdecimate=hi=64*12:lo=64*5:frac=0.1")

    cmd = ["ffmpeg", "-y", "-i", str(src), "-map", "0:v:0", "-map", "0:a?", "-map_metadata", "0"]
    if vf:
        cmd += ["-vf", ",".join(vf), "-fps_mode", "vfr"]
    cmd += ["-c:v", codec, "-crf", str(crf if crf is not None else default_crf)]
    if codec in {"libx264", "libx265"}:
        cmd += ["-preset", preset]
    else:
        cmd += ["-preset", preset]
    cmd += extra
    # Copy legacy audio whenever MP4-compatible; fall back to AAC if muxer rejects it.
    cmd += ["-c:a", "copy", "-movflags", "+faststart", str(dst)]
    try:
        run(cmd)
    except SSCError:
        cmd2 = [x for x in cmd]
        i = cmd2.index("-c:a")
        cmd2[i + 1] = "aac"
        cmd2[i+2:i+2] = ["-b:a", "160k"]
        run(cmd2)


def optimize_mp3(src: Path, dst: Path, profile: str) -> None:
    probe = ffprobe(src)
    a = stream_of(probe, "audio") or {}
    if profile == "compat":
        # Bitstream copy: exact MP3 audio, no generational loss. The SSC manifest
        # carries the new temporal-state information alongside it.
        run(["ffmpeg", "-y", "-i", str(src), "-vn", "-c:a", "copy", str(dst)])
        return

    # Opus usually provides better coding efficiency than MP3. Because transcoding
    # one lossy codec into another is never lossless, choose a bitrate that is lower
    # than the source rather than blindly making the file larger.
    try:
        src_bps = int(a.get("bit_rate") or probe.get("format", {}).get("bit_rate") or 128000)
    except (TypeError, ValueError):
        src_bps = 128000
    channels = int(a.get("channels") or 2)
    floor = 24000 if channels <= 1 else 48000
    cap = 96000 if profile == "efficient" else 64000
    target = max(floor, min(cap, int(src_bps * (0.72 if profile == "efficient" else 0.58))))
    # Round to whole kb/s for readable FFmpeg arguments.
    target_k = max(16, int(round(target / 1000.0)))
    run(["ffmpeg", "-y", "-i", str(src), "-vn", "-c:a", "libopus", "-b:a", f"{target_k}k",
         "-vbr", "on", "-compression_level", "10", str(dst)])


def cmd_analyze(args: argparse.Namespace) -> int:
    src = Path(args.input).expanduser().resolve()
    if not src.exists():
        raise SSCError(f"Input not found: {src}")
    manifest = make_manifest(src, analysis_fps=args.analysis_fps)
    out = Path(args.manifest).expanduser().resolve() if args.manifest else src.with_suffix(src.suffix + ".ssc.json")
    write_manifest(manifest, out)
    print(json.dumps({
        "manifest": str(out),
        "video_activity_ratio": manifest.get("video", {}).get("activity_ratio", {}),
        "audio_activity_ratio": manifest.get("audio", {}).get("activity_ratio", {}),
    }, indent=2))
    return 0


def cmd_encode(args: argparse.Namespace) -> int:
    src = Path(args.input).expanduser().resolve()
    if not src.exists():
        raise SSCError(f"Input not found: {src}")
    ext = src.suffix.lower()
    if ext not in {".mp4", ".mp3"}:
        raise SSCError("SSC v0.1 currently accepts .mp4 and .mp3 inputs")

    manifest = make_manifest(src, analysis_fps=args.analysis_fps)

    if args.output:
        dst = Path(args.output).expanduser().resolve()
    else:
        if ext == ".mp4":
            dst = src.with_name(src.stem + f".ssc-{args.profile}.mp4")
        elif args.profile == "compat":
            dst = src.with_name(src.stem + ".ssc-compat.mp3")
        else:
            dst = src.with_name(src.stem + f".ssc-{args.profile}.opus")

    if ext == ".mp4":
        optimize_mp4(src, dst, args.profile, args.collapse_static, args.crf)
    else:
        optimize_mp3(src, dst, args.profile)

    manifest["output"] = {
        "path": str(dst),
        "size_bytes": dst.stat().st_size,
        "profile": args.profile,
        "collapse_static": bool(args.collapse_static) if ext == ".mp4" else None,
        "note": (
            "MP4 timing is preserved; duplicate collapse uses VFR and never interpolates frames."
            if ext == ".mp4" else
            "MP3 is accepted as input. Efficient/max profiles transcode to Opus; compat remains MP3."
        ),
    }
    src_size = src.stat().st_size
    out_size = dst.stat().st_size
    manifest["output"]["size_change_percent"] = round((out_size / src_size - 1.0) * 100.0, 2) if src_size else 0.0

    mout = dst.with_suffix(dst.suffix + ".ssc.json")
    write_manifest(manifest, mout)

    print(json.dumps({
        "output": str(dst),
        "manifest": str(mout),
        "source_bytes": src_size,
        "output_bytes": out_size,
        "size_change_percent": manifest["output"]["size_change_percent"],
        "video_activity_ratio": manifest.get("video", {}).get("activity_ratio", {}),
        "audio_activity_ratio": manifest.get("audio", {}).get("activity_ratio", {}),
    }, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ssc_codec",
        description="SSC v0.1: legacy MP4/MP3 temporal-state analyser and optimizer",
    )
    p.add_argument("--version", action="version", version=f"SSC {VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("analyze", help="create an SSC temporal-state manifest without changing media")
    a.add_argument("input")
    a.add_argument("--manifest")
    a.add_argument("--analysis-fps", type=float, default=10.0)
    a.set_defaults(func=cmd_analyze)

    e = sub.add_parser("encode", help="analyse and create an optimized legacy-compatible output")
    e.add_argument("input")
    e.add_argument("-o", "--output")
    e.add_argument("--profile", choices=["compat", "efficient", "max"], default="efficient")
    e.add_argument("--analysis-fps", type=float, default=10.0)
    e.add_argument("--collapse-static", action="store_true",
                   help="MP4 only: conservatively collapse duplicate/near-duplicate frames into VFR holds")
    e.add_argument("--crf", type=int, default=None, help="override video CRF")
    e.set_defaults(func=cmd_encode)

    return p


def main() -> int:
    try:
        require_tool("ffmpeg")
        require_tool("ffprobe")
        args = build_parser().parse_args()
        return int(args.func(args))
    except SSCError as e:
        print(f"ssc_codec: error: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
