from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import LinoCodecError, analyze, play


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="casu", description="Casu — Codec All Segmented Unity: legacy-compatible MP4/MP3 segmented-state layer")
    p.add_argument("--version", action="version", version="Casu Codec All Segmented Unity 0.1.0")
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("analyze", help="write an SSC-compatible temporal-state sidecar")
    a.add_argument("input", type=Path)
    a.add_argument("-o", "--output", type=Path)
    a.add_argument("--analysis-fps", type=float, default=10.0)
    v = sub.add_parser("play", help="play legacy media through FFplay without changing it")
    v.add_argument("input", type=Path)
    v.add_argument("ffplay_args", nargs=argparse.REMAINDER)
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "analyze":
            if args.analysis_fps <= 0:
                raise LinoCodecError("analysis FPS must be positive")
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
        raise LinoCodecError("unknown command")
    except LinoCodecError as exc:
        print(f"casu: error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
