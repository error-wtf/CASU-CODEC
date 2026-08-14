# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Standalone CASUNAT2 acceptance.

A CASUNAT2 container must be fully usable (verify, info, open, play video,
play audio, seek) after being copied ALONE into a clean directory where the
original source does not exist.  This proves the modern CASU model never
depends on sidecars or original files.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from casu.native_v2 import read_native_v2  # noqa: E402
from mpcasu_native_backend import NativeCasuBackend  # noqa: E402


class _Video:
    def __init__(self):
        self.frames = 0

    def present(self, frame, pts_seconds):
        self.frames += 1

    def invalidate(self):
        pass

    def close(self):
        pass


class _Audio:
    def __init__(self):
        self.blocks = 0

    def write(self, block):
        self.blocks += 1

    def flush(self):
        pass

    def set_volume(self, volume):
        pass

    def set_mute(self, muted):
        pass

    def close(self):
        pass


@pytest.mark.media
def test_standalone_casunat2_in_clean_directory(tmp_path):
    source = ROOT / "test_media" / "demo_clip.mp4"
    if not source.is_file():
        pytest.skip("demo fixture missing")
    packed = tmp_path / "packed.casu"
    subprocess.run([sys.executable, "-m", "casu", "pack-v2", str(source),
                    "-o", str(packed)], check=True, cwd=ROOT,
                   capture_output=True, timeout=120)

    clean = tmp_path / "clean"
    clean.mkdir()
    alone = clean / "alone.casu"
    shutil.copy(packed, alone)

    container = read_native_v2(alone)
    assert container.integrity_verified

    info = subprocess.run([sys.executable, "-m", "casu", "native-info", str(alone)],
                          check=True, cwd=ROOT, capture_output=True, text=True)
    assert '"integrity_verified": true' in info.stdout

    video, audio = _Video(), _Audio()
    backend = NativeCasuBackend(video, audio)
    backend.open_casu(alone)
    backend.play()
    deadline = time.monotonic() + 20
    position = 0.0
    while time.monotonic() < deadline:
        position = max(position, backend.position())
        if position > 1.0:
            break
        time.sleep(0.05)
    assert position > 1.0, "standalone CASUNAT2 must play without its source"
    assert video.frames > 0
    assert audio.blocks > 0

    backend.seek(2.0)
    deadline = time.monotonic() + 10
    sought = 0.0
    while time.monotonic() < deadline:
        sought = backend.position()
        if abs(sought - 2.0) < 1.0:
            break
        time.sleep(0.05)
    assert abs(sought - 2.0) < 1.0, "seek must work on the standalone container"
    backend.close()
