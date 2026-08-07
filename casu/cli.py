from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import CasuError, analyze, play
from .schema import validate_manifest


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="casu", description="CASU — Codec for All Segmented Units: legacy-compatible MP4/MP3 segmented-state layer")
    p.add_argument("--version", action="version", version="CASU Codec for All Segmented Units 0.1.0")
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("analyze", help="write an SSC-compatible temporal-state sidecar")
    a.add_argument("input", type=Path)
    a.add_argument("-o", "--output", type=Path)
    a.add_argument("--analysis-fps", type=float, default=10.0)
    c = sub.add_parser("convert", help="convert legacy media to a CASU manifest without changing the source")
    c.add_argument("input", type=Path)
    c.add_argument("-o", "--output", type=Path)
    c.add_argument("--analysis-fps", type=float, default=10.0)
    v = sub.add_parser("play", help="play legacy media through FFplay without changing it")
    v.add_argument("input", type=Path)
    v.add_argument("ffplay_args", nargs=argparse.REMAINDER)
    x = sub.add_parser("validate", help="validate a .casu manifest")
    x.add_argument("manifest", type=Path)
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command in {"analyze", "convert"}:
            if args.analysis_fps <= 0:
                raise CasuError("analysis FPS must be positive")
            result = analyze(args.input, args.analysis_fps)
            output = args.output or args.input.with_suffix(args.input.suffix + ".casu")
            output = output.expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(json.dumps({"manifest": str(output), "duration_s": result["source"]["duration_s"],
                              "video_segments": len(result["video"].get("segments", [])),
                              "audio_segments": len(result["audio"].get("segments", []))}, indent=2))
            return 0
        if args.command == "play":
            play(args.input, args.ffplay_args)
            return 0
        if args.command == "validate":
            manifest = json.loads(args.manifest.expanduser().read_text(encoding="utf-8"))
            errors = validate_manifest(manifest)
            if errors:
                for error in errors:
                    print(f"INVALID: {error}")
                return 1
            print(f"VALID CASU manifest: {args.manifest}")
            return 0
        raise CasuError("unknown command")
    except CasuError as exc:
        print(f"casu: error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
