"""Pin the byte-identity of modules shared between CASU-CODEC and Casu-Player.

v7.8: 41 modules are intentionally byte-identical across both repositories.
This test fails loudly when one side drifts, so fixes must always be applied
to both (see ROADMAP_V7_8.md section 3.9).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SIBLING = ROOT.parent / "Casu-Player"

SHARED_MODULES = [
    # NOTE: casu/native.py, native_v2/{reader,video,audio,text,bitmap,attachment}.py are
    # intentionally DIFFERENT: the player repo ships decoder-only halves. They are pinned
    # by their own tests, not by byte identity.
    "casu/playlist.py",
    "casu/spotify.py",
    "casu/waveform.py",
    "casu/epg.py",
    "casu/search.py",
    "casu/schema.py",
    "casu/tags.py",
    "casu/thumbnail.py",
    "casu/settings.py",
    "casu/recording.py",
    "casu/libass.py",
    "casu/probe.py",
    "casu/scheduler.py",
    "casu/locations.py",
    "casu/media.py",
    "casu/youtube_groups.py",
    "casu/fileio.py",
    "casu/design.py",
    "casu/native_v2/format.py",
    "casu/native_v2/jsonutil.py",
    "casu/native_v2/validation.py",
    "casu/mp5/reader.py",
    "casu/mp5/format.py",
    "casu/strict/canonical.py",
    "casu/strict/model.py",
    "casu/strict/tiles.py",
    "mpcasu_backend.py",
    "mpcasu_native_backend.py",
    "mpcasu_playback.py",
    "mpcasu_qt/app.py",
    "mpcasu_qt/theme.py",
    "mpcasu_qt/videoframe.py",
    "mpcasu_qt/webplayers.py",
    "mpcasu_qt/youtube_proxy.py",
    "mpcasu_qt/browser_runtime.py",
]


@pytest.mark.skipif(not SIBLING.exists(), reason="Casu-Player sibling checkout absent")
@pytest.mark.parametrize("relative", SHARED_MODULES)
def test_shared_module_matches_player_mirror(relative: str) -> None:
    ours = (ROOT / relative).read_bytes()
    theirs = (SIBLING / "src" / "desktop" / relative).read_bytes()
    assert ours == theirs, (
        f"{relative} diverged between CASU-CODEC and Casu-Player — "
        "apply the change to both repositories"
    )
