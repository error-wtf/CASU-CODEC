# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path

from .core import ANALYSIS_MODES, CasuError, analyze, play, resolve_casu_source
from .schema import validate_manifest
from . import __version__


def atomic_write_text(path: Path, payload: str) -> None:
    """Write reports/manifests without exposing a partial destination file."""
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="casu", description="CASU — Codec for All Segmented Units: legacy-compatible MP4/MP3 segmented-state layer")
    p.add_argument("--version", action="version", version=f"CASU Codec for All Segmented Units {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("analyze", help="write a CASU temporal-state sidecar")
    a.add_argument("input", type=Path)
    a.add_argument("-o", "--output", type=Path)
    a.add_argument("--analysis-fps", type=float, default=10.0)
    a.add_argument("--mode", choices=sorted(ANALYSIS_MODES), default="strict",
                   help="state-analysis policy; strict is the reference mode")
    c = sub.add_parser("convert", help="convert legacy media to a CASU manifest without changing the source")
    c.add_argument("input", type=Path)
    c.add_argument("-o", "--output", type=Path)
    c.add_argument("--analysis-fps", type=float, default=10.0)
    c.add_argument("--mode", choices=sorted(ANALYSIS_MODES), default="strict",
                   help="state-analysis policy; strict is the reference mode")
    c.add_argument("--force", action="store_true", help="replace an existing output atomically")
    v = sub.add_parser("play", help="validate a media path for MPCASU in-process playback")
    v.add_argument("input", type=Path)
    x = sub.add_parser("validate", help="validate a .casu manifest")
    x.add_argument("manifest", type=Path)
    x.add_argument("--verify-source", action="store_true",
                   help="also resolve the recorded source and verify its SHA-256 digest")
    vfy = sub.add_parser("verify", help="validate a .casu manifest and verify its recorded source")
    vfy.add_argument("manifest", type=Path)
    info = sub.add_parser("info", help="print machine-readable CASU manifest information")
    info.add_argument("manifest", type=Path)
    b = sub.add_parser("benchmark", help="measure deterministic CASU analysis cost and emit a JSON report")
    b.add_argument("input", type=Path)
    b.add_argument("-o", "--output", type=Path, help="write the report JSON to this path")
    b.add_argument("--analysis-fps", type=float, default=10.0)
    b.add_argument("--mode", choices=sorted(ANALYSIS_MODES), default="strict")
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "benchmark":
            if args.analysis_fps <= 0:
                raise CasuError("analysis FPS must be positive")
            if not args.input.is_file():
                raise CasuError(f"input media does not exist: {args.input}")
            started = time.perf_counter()
            result = analyze(args.input, args.analysis_fps, args.mode)
            elapsed = time.perf_counter() - started
            report = {
                "report": "casu-benchmark-1",
                "input": str(args.input.expanduser().resolve()),
                "source_size_bytes": result["source"].get("size_bytes"),
                "duration_s": result["source"].get("duration_s"),
                "analysis_fps": args.analysis_fps,
                "analysis_mode": args.mode,
                "conversion_analysis_seconds": round(elapsed, 6),
                "video_segments": len(result.get("video", {}).get("segments", [])),
                "audio_segments": len(result.get("audio", {}).get("segments", [])),
                "energy_measurement": "unavailable",
                "notes": ["This report measures analysis cost; it does not claim energy savings."],
            }
            payload = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
            if args.output:
                atomic_write_text(args.output, payload)
            print(payload, end="")
            return 0
        if args.command in {"analyze", "convert"}:
            if args.analysis_fps <= 0:
                raise CasuError("analysis FPS must be positive")
            result = analyze(args.input, args.analysis_fps, args.mode)
            output = args.output or args.input.with_suffix(args.input.suffix + ".casu")
            output = output.expanduser().resolve()
            source_path = args.input.expanduser().resolve()
            if output == source_path:
                raise CasuError("output must differ from the source media; refusing to overwrite input")
            output.parent.mkdir(parents=True, exist_ok=True)
            if output.exists() and args.command == "convert" and not args.force:
                raise CasuError(f"output exists (use --force): {output}")
            payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
            atomic_write_text(output, payload)
            print(json.dumps({"manifest": str(output), "duration_s": result["source"]["duration_s"],
                              "video_segments": len(result["video"].get("segments", [])),
                              "audio_segments": len(result["audio"].get("segments", [])),
                              "mode": result["casu"]["analysis_mode"]}, indent=2))
            return 0
        if args.command == "play":
            play(args.input)
            return 0
        if args.command in {"validate", "verify", "info"}:
            try:
                manifest = json.loads(args.manifest.expanduser().read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise CasuError(f"could not read manifest {args.manifest}: {exc}") from exc
            errors = validate_manifest(manifest)
            if errors:
                if args.command == "info":
                    print(json.dumps({"valid": False, "errors": errors}, indent=2))
                    return 1
                for error in errors:
                    print(f"INVALID: {error}")
                return 1
            verify_source = args.command == "verify" or getattr(args, "verify_source", False)
            if verify_source:
                try:
                    source = resolve_casu_source(args.manifest)
                except CasuError as exc:
                    if args.command == "info":
                        print(json.dumps({"valid": False, "errors": [str(exc)]}, indent=2))
                        return 1
                    print(f"INVALID: {exc}")
                    return 1
                if args.command == "info":
                    print(json.dumps({"source_verified": str(source)}, indent=2))
                    return 0
                print(f"VERIFIED source: {source}")
            if args.command == "info":
                print(json.dumps({
                    "valid": True,
                    "manifest": str(args.manifest.expanduser().resolve()),
                    "format": manifest.get("format", {}),
                    "source": manifest.get("source", {}),
                    "streams": manifest.get("streams", []),
                    "video_segments": len(manifest.get("video", {}).get("segments", [])),
                    "audio_segments": len(manifest.get("audio", {}).get("segments", [])),
                    "integrity": manifest.get("integrity", {}),
                }, indent=2, ensure_ascii=False))
                return 0
            print(f"VALID CASU manifest: {args.manifest}")
            return 0
        raise CasuError("unknown command")
    except CasuError as exc:
        print(f"casu: error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
