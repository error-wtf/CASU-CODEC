#!/usr/bin/env python3
"""Small deterministic CASUNAT2 corruption campaign.

This is intentionally dependency-free so CI can run it without Atheris. It
mutates bounded byte positions and asserts that the reader either rejects the
input or returns a fully verified container; no exception escapes the target.
"""
from __future__ import annotations

import argparse
import random
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from casu.native_v2 import (ChunkType, NativeChunk, encode_bitmap_subtitle,
                            read_native_v2, write_native_v2)


def campaign(iterations: int = 10_000, seed: int = 0xCA5A) -> dict[str, int]:
    rng = random.Random(seed)
    with tempfile.TemporaryDirectory(prefix="casu-fuzz-") as directory:
        target = Path(directory) / "seed.casu"
        bitmap = encode_bitmap_subtitle(
            start_pts=0, end_pts=1000, canvas_width=2, canvas_height=2,
            x=0, y=0, width=2, height=2, rgba=b"\xff\x00\x00\xff" * 4)
        write_native_v2(target, {"format": "CASUNAT2", "streams": [0, 1, 2]}, [
            NativeChunk(ChunkType.STREAM_CONFIG, 0, 0, b"video:yuv420p"),
            NativeChunk(ChunkType.VIDEO_KEY_STATE, 0, 0, b"key-state"),
            NativeChunk(ChunkType.VIDEO_TILE_UPDATE, 0, 1, b"tile-update"),
            NativeChunk(ChunkType.AUDIO_BLOCK, 1, 0, b"audio-block"),
            NativeChunk(ChunkType.SUBTITLE_BITMAP, 2, 0, bitmap),
        ], recovery_interval=1)
        pristine = target.read_bytes()
        rejected = verified = unexpected = 0
        for _ in range(max(0, int(iterations))):
            mutated = bytearray(pristine)
            mode = rng.randrange(4)
            if mode == 0:
                mutated = mutated[:rng.randrange(len(mutated))]
            elif mode == 1:
                index = rng.randrange(len(mutated)); mutated[index] ^= 1 << rng.randrange(8)
            elif mode == 2:
                index = rng.randrange(8, min(len(mutated), 64)); mutated[index] = 255
            else:
                for _ in range(rng.randrange(1, 5)):
                    index = rng.randrange(len(mutated)); mutated[index] = rng.randrange(256)
            target.write_bytes(mutated)
            try:
                container = read_native_v2(target)
                if container.integrity_verified:
                    verified += 1
                else:
                    unexpected += 1
            except Exception:
                rejected += 1
        return {"iterations": iterations, "seed": seed, "rejected": rejected,
                "verified": verified, "unexpected": unexpected}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=10_000)
    parser.add_argument("--seed", type=lambda value: int(value, 0), default=0xCA5A,
                        help="deterministic random seed (decimal or 0x-prefixed)")
    args = parser.parse_args()
    result = campaign(args.iterations, seed=args.seed)
    print(result)
    return 0 if result["unexpected"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
