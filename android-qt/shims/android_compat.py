# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
"""Android replacement layer for the desktop tool pipeline.

The Linux player shells out to ffprobe/ffmpeg for probes, tags, covers,
waveform decoding and recording. Android has no such binaries; this shim
routes those calls through the Android platform instead:
  - probes/tags/covers  -> MediaMetadataRetriever (via pyjnius)
  - waveform PCM        -> libVLC audio callbacks (phase 2)
  - recording           -> not available initially (UI hides the action)
"""
from __future__ import annotations

_INSTALLED = False


def _ffprobe_shim(path: str) -> dict:
    """ffprobe replacement: MediaMetadataRetriever metadata as ffprobe-like
    JSON (the subset the player actually consumes)."""
    retriever = None
    try:
        from jnius import autoclass  # pyjnius, provided by the toolchain
        MediaMetadataRetriever = autoclass("android.media.MediaMetadataRetriever")
        retriever = MediaMetadataRetriever()
        retriever.setDataSource(path)
        tags = {
            "title": retriever.extractMetadata(2) or "",   # TITLE
            "artist": retriever.extractMetadata(3) or "",  # ARTIST
            "album": retriever.extractMetadata(4) or "",   # ALBUM
        }
        meta = {"format": {"filename": path, "tags": tags}}
        duration_ms = retriever.extractMetadata(1)  # DURATION
        if duration_ms:
            meta["format"]["duration"] = str(int(duration_ms) / 1000.0)
        return meta
    except Exception:
        return {"format": {"filename": path}}
    finally:
        if retriever is not None:
            try:
                retriever.release()
            except Exception:
                pass


def install() -> None:
    """Install Android shims into casu.core before the player imports.
    Idempotent; called once from main.py."""
    global _INSTALLED
    if _INSTALLED:
        return
    import shutil

    import casu.core as casu_core

    if not (shutil.which("ffprobe") or shutil.which("ffmpeg")):
        def ffprobe_compat(path=None, *args, **kwargs):
            return _ffprobe_shim(str(path or ""))

        if hasattr(casu_core, "ffprobe"):
            casu_core.ffprobe = ffprobe_compat

    _INSTALLED = True
