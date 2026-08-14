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

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from casu.native_v2 import (ChunkType, NativeChunk, encode_audio_block,
                            encode_bitmap_subtitle, encode_key_state,
                            encode_tile_update, read_native_v2,
                            write_native_v2)
from casu.strict import canonical_frame


def campaign(iterations: int = 10_000, seed: int = 0xCA5A) -> dict[str, int]:
    rng = random.Random(seed)
    with tempfile.TemporaryDirectory(prefix="casu-fuzz-") as directory:
        target = Path(directory) / "seed.casu"
        bitmap = encode_bitmap_subtitle(
            start_pts=0, end_pts=1000, canvas_width=2, canvas_height=2,
            x=0, y=0, width=2, height=2, rgba=b"\xff\x00\x00\xff" * 4)
        first = canonical_frame(np.zeros((2, 6), dtype=np.uint8),
                                pixel_format="rgb24", source_shape=(2, 2))
        changed_pixels = np.zeros((2, 6), dtype=np.uint8)
        changed_pixels[0, :3] = 7
        changed = canonical_frame(changed_pixels, pixel_format="rgb24",
                                  source_shape=(2, 2))
        video = {"stream_id": 1, "type": "video", "time_base": [1, 1000],
                 "width": 2, "height": 2, "pix_fmt": "rgb24"}
        audio = {"stream_id": 2, "type": "audio", "time_base": [1, 1000],
                 "sample_rate": 1000, "channels": 1}
        subtitle = {"stream_id": 3, "type": "subtitle",
                    "time_base": [1, 1000]}
        write_native_v2(target, {"format": "CASUNAT2", "version": 2,
                                 "streams": [video, audio, subtitle]}, [
            NativeChunk(ChunkType.VIDEO_KEY_STATE, 1, 0,
                        encode_key_state(first)),
            NativeChunk(ChunkType.VIDEO_TILE_UPDATE, 1, 1,
                        encode_tile_update(changed, x=0, y=0,
                                           width=2, height=1)),
            NativeChunk(ChunkType.AUDIO_BLOCK, 2, 0, encode_audio_block(
                pcm=b"\0\0", pts=0, time_base_num=1, time_base_den=1000,
                sample_rate=1000, channels=1, sample_count=1)),
            NativeChunk(ChunkType.SUBTITLE_BITMAP, 3, 0, bitmap),
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
