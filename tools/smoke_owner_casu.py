# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Native CASUNAT2 playback smoke on owner reference fixtures.

Plays the owner's test-pattern video and audio track from their CASUNAT2
containers through NativeCasuBackend with instrumented sinks: position must
exceed 1 s and a mid-file seek must land near the requested offset.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from mpcasu_backend import PlaybackState  # noqa: E402
from mpcasu_native_backend import NativeCasuBackend  # noqa: E402


class VideoSink:
    def __init__(self) -> None:
        self.frames = 0
        self.invalidations = 0

    def present(self, frame, pts_seconds):
        self.frames += 1

    def invalidate(self):
        self.invalidations += 1

    def close(self):
        pass


class AudioSink:
    def __init__(self) -> None:
        self.blocks = 0
        self.flushes = 0
        self.volume = 100
        self.muted = False

    def write(self, block):
        self.blocks += 1

    def flush(self):
        self.flushes += 1

    def set_volume(self, volume):
        self.volume = volume

    def set_mute(self, muted):
        self.muted = muted

    def close(self):
        pass


def check(path: Path, seek_to: float) -> bool:
    video, audio = VideoSink(), AudioSink()
    backend = NativeCasuBackend(video, audio)
    backend.open_casu(path)
    backend.play()
    deadline = time.monotonic() + 60.0
    position = 0.0
    while time.monotonic() < deadline:
        state = backend.state()
        position = max(position, backend.position())
        if position > 1.0 or state in (PlaybackState.ERROR, PlaybackState.ENDED):
            break
        time.sleep(0.05)
    ok = position > 1.0 and backend.state() != PlaybackState.ERROR
    seek_ok = False
    if ok and seek_to > 0:
        backend.seek(seek_to)
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            moved = backend.position()
            if abs(moved - seek_to) < 5.0:
                seek_ok = True
                break
            if backend.state() == PlaybackState.ERROR:
                break
            time.sleep(0.05)
    backend.close()
    label = path.name
    print(f"[{'OK' if ok else 'FAIL'}] {label}: pos={position:.2f}s "
          f"frames={video.frames} audio_blocks={audio.blocks}")
    if seek_to > 0:
        print(f"[{'OK' if seek_ok else 'FAIL'}] {label}: seek {seek_to:.0f}s")
    return ok and (seek_to <= 0 or seek_ok)


def main() -> int:
    results = [
        check(root / "test_media" / "lino_lol_test_pattern.nat2.casu", 60.0),
        check(root / "test_media" / "lino_casu_error.nat2.casu", 120.0),
    ]
    print("OWNER CASU SMOKE:", "PASS" if all(results) else "FAIL")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
