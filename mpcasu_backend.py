# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Internal MPCASU playback backends.

The backend uses libVLC through its shared library API.  No player executable
is launched: decoding, clocking, seeking and video-window ownership remain
under MPCASU control.  CASU manifests are validated before their immutable
source is opened by the same in-process media pipeline.
"""
from __future__ import annotations

import ctypes
import os
import sys
from enum import Enum
from pathlib import Path

from casu.core import CasuError, resolve_casu_source
from casu.schema import validate_manifest
import json


class PlaybackState(str, Enum):
    EMPTY = "EMPTY"; LOADING = "LOADING"; READY = "READY"
    PLAYING = "PLAYING"; PAUSED = "PAUSED"; STOPPED = "STOPPED"
    ENDED = "ENDED"; ERROR = "ERROR"


class BackendError(CasuError):
    pass


class LibVLCBackend:
    """Minimal, real in-process libVLC backend for the MPCASU window."""

    def __init__(self, video_widget):
        # Python/ctypes does not inherit the plugin-path setup that the VLC
        # launcher normally performs. Point libVLC at its installed modules so
        # H.264/AAC and other codecs are discovered by the in-process player.
        plugin_path = "/usr/lib/x86_64-linux-gnu/vlc/plugins"
        if os.path.isdir(plugin_path):
            os.environ.setdefault("VLC_PLUGIN_PATH", plugin_path)
        try:
            self.lib = ctypes.CDLL("libvlc.so.5")
        except OSError as exc:
            raise BackendError("libVLC shared library is unavailable") from exc
        self.widget = video_widget
        options = [b"--no-video-title-show"]
        if os.path.isdir(plugin_path):
            options.append(("--plugin-path=" + plugin_path).encode())
        argv = (ctypes.c_char_p * len(options))(*options)
        self.instance = self._call("libvlc_new", ctypes.c_void_p, [ctypes.c_int, ctypes.POINTER(ctypes.c_char_p)])(len(options), argv)
        if not self.instance:
            raise BackendError("libVLC could not be initialized")
        self.media = None; self.player = None; self.path: Path | None = None
        self._state = PlaybackState.EMPTY
        self._install("libvlc_media_new_path", ctypes.c_void_p, [ctypes.c_void_p, ctypes.c_char_p])
        self._install("libvlc_media_player_new_from_media", ctypes.c_void_p, [ctypes.c_void_p])
        self._install("libvlc_media_player_release", None, [ctypes.c_void_p])
        self._install("libvlc_media_release", None, [ctypes.c_void_p])
        self._install("libvlc_release", None, [ctypes.c_void_p])
        self._install("libvlc_media_player_play", ctypes.c_int, [ctypes.c_void_p])
        self._install("libvlc_media_player_set_pause", None, [ctypes.c_void_p, ctypes.c_int])
        self._install("libvlc_media_player_stop", None, [ctypes.c_void_p])
        self._install("libvlc_media_player_is_playing", ctypes.c_int, [ctypes.c_void_p])
        self._install("libvlc_media_player_get_time", ctypes.c_int64, [ctypes.c_void_p])
        self._install("libvlc_media_player_get_length", ctypes.c_int64, [ctypes.c_void_p])
        self._install("libvlc_media_player_set_time", None, [ctypes.c_void_p, ctypes.c_int64])
        self._install("libvlc_audio_set_volume", ctypes.c_int, [ctypes.c_void_p, ctypes.c_int])
        self._install("libvlc_audio_get_volume", ctypes.c_int, [ctypes.c_void_p])
        self._install("libvlc_audio_set_mute", None, [ctypes.c_void_p, ctypes.c_int])
        if sys.platform.startswith("linux"):
            self._install("libvlc_media_player_set_xwindow", None, [ctypes.c_void_p, ctypes.c_uint32])

    def _install(self, name, restype, args):
        setattr(self, name, self._call(name, restype, args))

    def _call(self, name, restype, args):
        try: function = getattr(self.lib, name)
        except AttributeError as exc: raise BackendError(f"libVLC API missing: {name}") from exc
        function.restype = restype; function.argtypes = args
        return function

    def open(self, path: Path) -> None:
        self.close_media()
        self.path = path.resolve(); self._state = PlaybackState.LOADING
        self.media = self.libvlc_media_new_path(self.instance, os_path(self.path))
        if not self.media: self._state = PlaybackState.ERROR; raise BackendError(f"libVLC could not open {path}")
        self.player = self.libvlc_media_player_new_from_media(self.media)
        if not self.player: self._state = PlaybackState.ERROR; raise BackendError("libVLC could not create media player")
        if sys.platform.startswith("linux"):
            self.libvlc_media_player_set_xwindow(self.player, self.widget.winfo_id())
        self._state = PlaybackState.READY

    def play(self):
        if not self.player or self.libvlc_media_player_play(self.player) != 0: raise BackendError("libVLC playback could not start")
        self._state = PlaybackState.PLAYING

    def pause(self):
        if self.player: self.libvlc_media_player_set_pause(self.player, 1); self._state = PlaybackState.PAUSED

    def resume(self):
        if self.player: self.libvlc_media_player_set_pause(self.player, 0); self._state = PlaybackState.PLAYING

    def stop(self):
        if self.player: self.libvlc_media_player_stop(self.player)
        self._state = PlaybackState.STOPPED

    def seek(self, seconds: float):
        if self.player: self.libvlc_media_player_set_time(self.player, int(max(0.0, seconds) * 1000))

    def position(self) -> float:
        return max(0.0, float(self.libvlc_media_player_get_time(self.player) if self.player else 0) / 1000.0)

    def duration(self) -> float:
        return max(0.0, float(self.libvlc_media_player_get_length(self.player) if self.player else 0) / 1000.0)

    def state(self) -> PlaybackState:
        if self.player and self._state == PlaybackState.PLAYING and not self.libvlc_media_player_is_playing(self.player):
            if self.duration() and self.position() >= self.duration() - 0.2: self._state = PlaybackState.ENDED
        return self._state

    def set_volume(self, value: int) -> int:
        if not self.player: return 0
        value = max(0, min(200, int(value)))
        if self.libvlc_audio_set_volume(self.player, value) != 0:
            raise BackendError("libVLC rejected the requested volume")
        return value

    def volume(self) -> int:
        return max(0, int(self.libvlc_audio_get_volume(self.player) if self.player else 0))

    def set_mute(self, muted: bool) -> None:
        if self.player: self.libvlc_audio_set_mute(self.player, int(bool(muted)))

    def close_media(self):
        if self.player: self.libvlc_media_player_stop(self.player); self.libvlc_media_player_release(self.player)
        if self.media: self.libvlc_media_release(self.media)
        self.player = self.media = None

    def close(self):
        self.close_media()
        if self.instance: self.libvlc_release(self.instance)
        self.instance = None; self._state = PlaybackState.EMPTY


class CasuBackend(LibVLCBackend):
    """Validated CASU sidecar path with immutable source provenance."""

    def open_casu(self, manifest_path: Path) -> None:
        try: manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc: raise BackendError(f"invalid CASU manifest: {manifest_path}") from exc
        errors = validate_manifest(manifest)
        if errors: raise BackendError(f"invalid CASU manifest: {errors[0]}")
        self.open(resolve_casu_source(manifest_path))


def os_path(path: Path) -> bytes:
    return str(path).encode(sys.getfilesystemencoding(), errors="surrogateescape")
