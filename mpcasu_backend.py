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
from urllib.parse import urlparse


class PlaybackState(str, Enum):
    EMPTY = "EMPTY"; LOADING = "LOADING"; READY = "READY"
    PLAYING = "PLAYING"; PAUSED = "PAUSED"; STOPPED = "STOPPED"
    ENDED = "ENDED"; ERROR = "ERROR"


class BackendError(CasuError):
    pass


class _TrackDescription(ctypes.Structure):
    _fields_ = [("identifier", ctypes.c_int), ("name", ctypes.c_char_p)]


class LibVLCBackend:
    """Minimal, real in-process libVLC backend for the MPCASU window."""

    def __init__(self, video_widget):
        # Python/ctypes does not inherit the plugin-path setup that the VLC
        # launcher normally performs. Point libVLC at its installed modules so
        # H.264/AAC and other codecs are discovered by the in-process player.
        plugin_candidates = []
        configured_plugins = os.environ.get("VLC_PLUGIN_PATH")
        if configured_plugins:
            plugin_candidates.append(configured_plugins)
        if sys.platform.startswith("linux"):
            plugin_candidates.extend(("/usr/lib/x86_64-linux-gnu/vlc/plugins", "/usr/lib/vlc/plugins"))
        elif sys.platform == "darwin":
            plugin_candidates.append("/Applications/VLC.app/Contents/MacOS/plugins")
        plugin_path = next((candidate for candidate in plugin_candidates if os.path.isdir(candidate)), None)
        if plugin_path:
            os.environ.setdefault("VLC_PLUGIN_PATH", plugin_path)
        library_names = (["libvlc.dll", "libvlc-5.dll"] if sys.platform.startswith("win")
                         else ["libvlc.dylib"] if sys.platform == "darwin"
                         else ["libvlc.so.5", "libvlc.so"])
        load_error = None
        for library_name in library_names:
            try:
                self.lib = ctypes.CDLL(library_name)
                break
            except OSError as exc:
                load_error = exc
        else:
            raise BackendError("libVLC shared library is unavailable") from load_error
        self.widget = video_widget
        # VLC 3.x discovers modules through VLC_PLUGIN_PATH. The historical
        # --plugin-path command-line option is no longer accepted and can
        # prevent codec modules from loading in embedded libVLC builds.
        options = [b"--no-video-title-show"]
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
        self._install("libvlc_media_player_set_rate", ctypes.c_int, [ctypes.c_void_p, ctypes.c_float])
        self._install("libvlc_media_player_get_rate", ctypes.c_float, [ctypes.c_void_p])
        self._install("libvlc_audio_set_volume", ctypes.c_int, [ctypes.c_void_p, ctypes.c_int])
        self._install("libvlc_audio_get_volume", ctypes.c_int, [ctypes.c_void_p])
        self._install("libvlc_audio_set_mute", None, [ctypes.c_void_p, ctypes.c_int])
        self._install("libvlc_audio_get_track_count", ctypes.c_int, [ctypes.c_void_p])
        self._install("libvlc_audio_get_track", ctypes.c_int, [ctypes.c_void_p])
        self._install("libvlc_audio_set_track", ctypes.c_int, [ctypes.c_void_p, ctypes.c_int])
        self._audio_description_api = self._install_descriptions("libvlc_audio_get_track_description")
        self._video_track_api = all(self._optional_install(name, restype, args) for name, restype, args in (
            ("libvlc_video_get_track_count", ctypes.c_int, [ctypes.c_void_p]),
            ("libvlc_video_get_track", ctypes.c_int, [ctypes.c_void_p]),
            ("libvlc_video_set_track", ctypes.c_int, [ctypes.c_void_p, ctypes.c_int]),
        ))
        self._video_description_api = self._install_descriptions("libvlc_video_get_track_description")
        self._subtitle_api = all(self._optional_install(name, restype, args) for name, restype, args in (
            ("libvlc_video_get_spu_count", ctypes.c_int, [ctypes.c_void_p]),
            ("libvlc_video_get_spu", ctypes.c_int, [ctypes.c_void_p]),
            ("libvlc_video_set_spu", ctypes.c_int, [ctypes.c_void_p, ctypes.c_int]),
        ))
        self._subtitle_description_api = self._install_descriptions("libvlc_video_get_spu_description")
        if sys.platform.startswith("linux"):
            self._install("libvlc_media_player_set_xwindow", None, [ctypes.c_void_p, ctypes.c_uint32])
        elif sys.platform.startswith("win"):
            self._install("libvlc_media_player_set_hwnd", None, [ctypes.c_void_p, ctypes.c_void_p])
        elif sys.platform == "darwin":
            self._install("libvlc_media_player_set_nsobject", None, [ctypes.c_void_p, ctypes.c_void_p])

    def _install(self, name, restype, args):
        setattr(self, name, self._call(name, restype, args))

    def _optional_install(self, name, restype, args) -> bool:
        try:
            self._install(name, restype, args)
        except BackendError:
            return False
        return True

    def _install_descriptions(self, name) -> bool:
        try:
            self._install(name, ctypes.POINTER(_TrackDescription), [ctypes.c_void_p])
            self._install("libvlc_track_description_release", None, [ctypes.POINTER(_TrackDescription)])
        except BackendError:
            return False
        return True

    def _call(self, name, restype, args):
        try: function = getattr(self.lib, name)
        except AttributeError as exc: raise BackendError(f"libVLC API missing: {name}") from exc
        function.restype = restype; function.argtypes = args
        return function

    @staticmethod
    def supports(source: str | Path) -> bool:
        """Return whether the universal backend can accept this source form."""
        value = str(source)
        parsed = urlparse(value)
        return isinstance(source, Path) or not parsed.scheme or parsed.scheme in {
            "file", "http", "https", "rtsp", "rtp", "udp", "ftp", "smb"
        }

    def capabilities(self) -> dict[str, str]:
        """Expose runtime facts instead of claiming a static format matrix."""
        version = self._call("libvlc_get_version", ctypes.c_char_p, [])()
        return {
            "backend": "libVLC shared library",
            "version": version.decode("utf-8", "replace") if version else "unknown",
            "network": "available",
            "hardware_decode": "delegated to installed libVLC modules",
            "player_process": "none",
        }

    def open(self, path: Path) -> None:
        self.open_source(path)

    def open_source(self, source: str | Path) -> None:
        if not self.supports(source):
            raise BackendError(f"unsupported media source: {source}")
        self.close_media()
        self.path = Path(source).resolve() if isinstance(source, Path) else None
        self._state = PlaybackState.LOADING
        value = str(source)
        parsed = urlparse(value)
        if parsed.scheme and parsed.scheme != "file":
            self._install("libvlc_media_new_location", ctypes.c_void_p, [ctypes.c_void_p, ctypes.c_char_p])
            self.media = self.libvlc_media_new_location(self.instance, value.encode("utf-8"))
        else:
            local = self.path or Path(parsed.path)
            self.media = self.libvlc_media_new_path(self.instance, os_path(local))
        if not self.media: self._state = PlaybackState.ERROR; raise BackendError(f"libVLC could not open {source}")
        self.player = self.libvlc_media_player_new_from_media(self.media)
        if not self.player: self._state = PlaybackState.ERROR; raise BackendError("libVLC could not create media player")
        if sys.platform.startswith("linux"):
            self.libvlc_media_player_set_xwindow(self.player, self.widget.winfo_id())
        elif sys.platform.startswith("win"):
            self.libvlc_media_player_set_hwnd(self.player, ctypes.c_void_p(self.widget.winfo_id()))
        elif sys.platform == "darwin":
            self.libvlc_media_player_set_nsobject(self.player, ctypes.c_void_p(self.widget.winfo_id()))
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

    def set_rate(self, rate: float) -> float:
        if not self.player:
            raise BackendError("no active media player")
        rate = max(0.25, min(4.0, float(rate)))
        if self.libvlc_media_player_set_rate(self.player, ctypes.c_float(rate)) == -1:
            raise BackendError("libVLC rejected playback rate")
        return float(self.libvlc_media_player_get_rate(self.player))

    def rate(self) -> float:
        return float(self.libvlc_media_player_get_rate(self.player)) if self.player else 1.0

    def position(self) -> float:
        return max(0.0, float(self.libvlc_media_player_get_time(self.player) if self.player else 0) / 1000.0)

    def duration(self) -> float:
        return max(0.0, float(self.libvlc_media_player_get_length(self.player) if self.player else 0) / 1000.0)

    def state(self) -> PlaybackState:
        if self.player and self._state == PlaybackState.PLAYING and not self.libvlc_media_player_is_playing(self.player):
            if self.duration() and self.position() >= self.duration() - 0.2: self._state = PlaybackState.ENDED
        return self._state

    def is_actively_playing(self) -> bool:
        """Return the backend's real playing flag, not just requested state."""
        return bool(self.player and self.libvlc_media_player_is_playing(self.player))

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

    def audio_track_count(self) -> int:
        return max(0, int(self.libvlc_audio_get_track_count(self.player) if self.player else 0))

    def audio_track(self) -> int:
        return int(self.libvlc_audio_get_track(self.player) if self.player else -1)

    def set_audio_track(self, track: int) -> None:
        if self.player and self.libvlc_audio_set_track(self.player, int(track)) != 0:
            raise BackendError(f"libVLC rejected audio track {track}")

    def audio_track_descriptions(self) -> list[tuple[int, str]]:
        return self._track_descriptions(self.libvlc_audio_get_track_description) if self._audio_description_api and self.player else []

    def video_track_count(self) -> int:
        return max(0, int(self.libvlc_video_get_track_count(self.player) if self._video_track_api and self.player else 0))

    def video_track(self) -> int:
        return int(self.libvlc_video_get_track(self.player) if self._video_track_api and self.player else -1)

    def set_video_track(self, track: int) -> None:
        if not self._video_track_api:
            raise BackendError("video track selection is unavailable in this libVLC build")
        if self.player and self.libvlc_video_set_track(self.player, int(track)) != 0:
            raise BackendError(f"libVLC rejected video track {track}")

    def video_track_descriptions(self) -> list[tuple[int, str]]:
        return self._track_descriptions(self.libvlc_video_get_track_description) if self._video_description_api and self.player else []

    def subtitle_track_count(self) -> int:
        if not self._subtitle_api:
            return 0
        return max(0, int(self.libvlc_video_get_spu_count(self.player) if self.player else 0))

    def subtitle_track(self) -> int:
        if not self._subtitle_api:
            return -1
        return int(self.libvlc_video_get_spu(self.player) if self.player else -1)

    def set_subtitle_track(self, track: int) -> None:
        if not self._subtitle_api:
            raise BackendError("subtitle selection is unavailable in this libVLC build")
        if self.player and self.libvlc_video_set_spu(self.player, int(track)) != 0:
            raise BackendError(f"libVLC rejected subtitle track {track}")

    def subtitle_track_descriptions(self) -> list[tuple[int, str]]:
        return self._track_descriptions(self.libvlc_video_get_spu_description) if self._subtitle_description_api and self.player else []

    def _track_descriptions(self, getter) -> list[tuple[int, str]]:
        pointer = getter(self.player)
        if not pointer:
            return []
        values: list[tuple[int, str]] = []
        try:
            index = 0
            while index < 256:
                item = pointer[index]
                if item.identifier == -1:
                    break
                values.append((int(item.identifier), (item.name or b"").decode("utf-8", "replace")))
                index += 1
        finally:
            self.libvlc_track_description_release(pointer)
        return values

    def close_media(self):
        if self.player: self.libvlc_media_player_stop(self.player); self.libvlc_media_player_release(self.player)
        if self.media: self.libvlc_media_release(self.media)
        self.player = self.media = None

    def close(self):
        self.close_media()
        if self.instance: self.libvlc_release(self.instance)
        self.instance = None; self._state = PlaybackState.EMPTY


class CasuBackend(LibVLCBackend):
    """Validated CASU sidecar path with immutable source provenance.

    This is intentionally named as a compatibility path until CASU has a
    native payload decoder; capability reporting must not imply otherwise.
    """

    def capabilities(self) -> dict[str, str]:
        values = super().capabilities()
        values.update({"backend_path": "CASU sidecar compatibility", "native_casu_payload": "unavailable"})
        return values

    def open_casu(self, manifest_path: Path) -> None:
        try: manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc: raise BackendError(f"invalid CASU manifest: {manifest_path}") from exc
        errors = validate_manifest(manifest)
        if errors: raise BackendError(f"invalid CASU manifest: {errors[0]}")
        self.open(resolve_casu_source(manifest_path))


def os_path(path: Path) -> bytes:
    return str(path).encode(sys.getfilesystemencoding(), errors="surrogateescape")
