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
import ctypes.util
import os
import sys
import tempfile
from enum import Enum
from pathlib import Path
from typing import Any

from casu.core import CasuError, resolve_casu_source
from casu.schema import validate_manifest
from casu.native import NativeCasuError, read_native
from casu.media import (AudioDeviceDescriptor, ChapterDescriptor,
                        TrackDescriptor, TrackKind)
import json
from urllib.parse import urlparse


class PlaybackState(str, Enum):
    EMPTY = "EMPTY"; LOADING = "LOADING"; READY = "READY"
    PLAYING = "PLAYING"; PAUSED = "PAUSED"; STOPPED = "STOPPED"
    ENDED = "ENDED"; ERROR = "ERROR"


# Stable libvlc_event_e media-player values used by libVLC 2.x/3.x/4.x.
# Keep this table explicit and tested: confusing EndReached (0x109) with
# EncounteredError (0x10A) makes successful playback look like a decoder fault.
LIBVLC_PLAYER_EVENT_STATES = {
    0x102: PlaybackState.LOADING,  # MediaPlayerOpening
    0x103: PlaybackState.LOADING,  # MediaPlayerBuffering
    0x104: PlaybackState.PLAYING,  # MediaPlayerPlaying
    0x105: PlaybackState.PAUSED,   # MediaPlayerPaused
    0x106: PlaybackState.STOPPED,  # MediaPlayerStopped
    0x109: PlaybackState.ENDED,    # MediaPlayerEndReached
    0x10A: PlaybackState.ERROR,    # MediaPlayerEncounteredError
}


class BackendError(CasuError):
    pass


class _TrackDescription(ctypes.Structure):
    _fields_ = [("identifier", ctypes.c_int), ("name", ctypes.c_char_p)]


class _AudioOutputDevice(ctypes.Structure):
    pass


_AudioOutputDevice._fields_ = [
    ("next", ctypes.POINTER(_AudioOutputDevice)),
    ("device", ctypes.c_char_p),
    ("description", ctypes.c_char_p),
]


class LibVLCBackend:
    """Minimal, real in-process libVLC backend for the MPCASU window."""

    def __init__(self, video_widget, *, runtime_options: tuple[str, ...] = ()):
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
        library_names = self.library_candidates(sys.platform)
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
        self.runtime_options = self.validate_runtime_options(runtime_options)
        # VLC 3.x discovers modules through VLC_PLUGIN_PATH. The historical
        # --plugin-path command-line option is no longer accepted and can
        # prevent codec modules from loading in embedded libVLC builds.
        options = [b"--no-video-title-show", *(
            value.encode("utf-8") for value in self.runtime_options)]
        argv = (ctypes.c_char_p * len(options))(*options)
        self.instance = self._call("libvlc_new", ctypes.c_void_p, [ctypes.c_int, ctypes.POINTER(ctypes.c_char_p)])(len(options), argv)
        if not self.instance:
            raise BackendError("libVLC could not be initialized")
        self.media = None; self.player = None; self.path: Path | None = None
        self._native_temp: Path | None = None
        self._state = PlaybackState.EMPTY
        self._event_manager = None
        self._event_callback_type = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)
        self._event_callbacks: list[tuple[int, Any]] = []
        self._event_api = False
        self.on_event = None
        self._install("libvlc_media_new_path", ctypes.c_void_p, [ctypes.c_void_p, ctypes.c_char_p])
        self._subtitle_option_api = self._optional_install("libvlc_media_add_option", None, [ctypes.c_void_p, ctypes.c_char_p])
        self._install("libvlc_media_player_new_from_media", ctypes.c_void_p, [ctypes.c_void_p])
        self._install("libvlc_media_player_release", None, [ctypes.c_void_p])
        self._install("libvlc_media_release", None, [ctypes.c_void_p])
        self._install("libvlc_release", None, [ctypes.c_void_p])
        self._media_state_api = self._optional_install("libvlc_media_get_state", ctypes.c_int, [ctypes.c_void_p])
        self._install("libvlc_media_player_play", ctypes.c_int, [ctypes.c_void_p])
        self._install("libvlc_media_player_set_pause", None, [ctypes.c_void_p, ctypes.c_int])
        self._install("libvlc_media_player_stop", None, [ctypes.c_void_p])
        self._install("libvlc_media_player_is_playing", ctypes.c_int, [ctypes.c_void_p])
        self._install("libvlc_media_player_get_time", ctypes.c_int64, [ctypes.c_void_p])
        self._install("libvlc_media_player_get_length", ctypes.c_int64, [ctypes.c_void_p])
        self._install("libvlc_media_player_set_time", None, [ctypes.c_void_p, ctypes.c_int64])
        self._chapter_api = all(self._optional_install(name, restype, args) for name, restype, args in (
            ("libvlc_media_player_get_title_count", ctypes.c_int, [ctypes.c_void_p]),
            ("libvlc_media_player_get_title", ctypes.c_int, [ctypes.c_void_p]),
            ("libvlc_media_player_set_title", ctypes.c_int, [ctypes.c_void_p, ctypes.c_int]),
            ("libvlc_media_player_get_chapter_count", ctypes.c_int, [ctypes.c_void_p, ctypes.c_int]),
            ("libvlc_media_player_get_chapter", ctypes.c_int, [ctypes.c_void_p]),
            ("libvlc_media_player_set_chapter", ctypes.c_int, [ctypes.c_void_p, ctypes.c_int]),
        ))
        self._frame_step_api = self._optional_install("libvlc_media_player_next_frame", ctypes.c_int, [ctypes.c_void_p])
        self._install("libvlc_media_player_set_rate", ctypes.c_int, [ctypes.c_void_p, ctypes.c_float])
        self._install("libvlc_media_player_get_rate", ctypes.c_float, [ctypes.c_void_p])
        self._install("libvlc_audio_set_volume", ctypes.c_int, [ctypes.c_void_p, ctypes.c_int])
        self._install("libvlc_audio_get_volume", ctypes.c_int, [ctypes.c_void_p])
        self._install("libvlc_audio_set_mute", None, [ctypes.c_void_p, ctypes.c_int])
        self._audio_delay_api = self._optional_install(
            "libvlc_audio_set_delay", ctypes.c_int,
            [ctypes.c_void_p, ctypes.c_int64])
        self._install("libvlc_audio_get_track_count", ctypes.c_int, [ctypes.c_void_p])
        self._install("libvlc_audio_get_track", ctypes.c_int, [ctypes.c_void_p])
        self._install("libvlc_audio_set_track", ctypes.c_int, [ctypes.c_void_p, ctypes.c_int])
        self._audio_description_api = self._install_descriptions("libvlc_audio_get_track_description")
        self._audio_device_api = all(self._optional_install(name, restype, args) for name, restype, args in (
            ("libvlc_audio_output_device_enum", ctypes.POINTER(_AudioOutputDevice), [ctypes.c_void_p]),
            ("libvlc_audio_output_device_list_release", None, [ctypes.POINTER(_AudioOutputDevice)]),
            ("libvlc_audio_output_device_set", None, [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]),
        ))
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
        self._subtitle_delay_api = self._optional_install(
            "libvlc_video_set_spu_delay", ctypes.c_int,
            [ctypes.c_void_p, ctypes.c_int64])
        self._event_api = all(self._optional_install(name, restype, args) for name, restype, args in (
            ("libvlc_media_player_event_manager", ctypes.c_void_p, [ctypes.c_void_p]),
            ("libvlc_event_attach", ctypes.c_int, [ctypes.c_void_p, ctypes.c_uint, self._event_callback_type, ctypes.c_void_p]),
            ("libvlc_event_detach", None, [ctypes.c_void_p, ctypes.c_uint, self._event_callback_type, ctypes.c_void_p]),
        ))
        if sys.platform.startswith("linux"):
            self._install("libvlc_media_player_set_xwindow", None, [ctypes.c_void_p, ctypes.c_uint32])
        elif sys.platform.startswith("win"):
            self._install("libvlc_media_player_set_hwnd", None, [ctypes.c_void_p, ctypes.c_void_p])
        elif sys.platform == "darwin":
            self._install("libvlc_media_player_set_nsobject", None, [ctypes.c_void_p, ctypes.c_void_p])

    @staticmethod
    def library_candidates(platform: str) -> list[str]:
        if platform.startswith("win"):
            return ["libvlc.dll", "libvlc-5.dll"]
        if platform == "darwin":
            return ["libvlc.dylib"]
        discovered = ctypes.util.find_library("vlc")
        return list(dict.fromkeys(value for value in
                                  (discovered, "libvlc.so.5", "libvlc.so") if value))

    @staticmethod
    def validate_runtime_options(options: tuple[str, ...]) -> tuple[str, ...]:
        """Bound explicit libVLC options used by controlled runtime probes.

        Production callers normally pass no options. The hook lets the codec
        matrix select dummy audio/video sinks and exercise demuxing, decoding
        and clock progression independently of physical host devices.
        """
        if not isinstance(options, tuple):
            raise BackendError("libVLC runtime options must be a tuple")
        if len(options) > 16:
            raise BackendError("too many libVLC runtime options")
        validated: list[str] = []
        for value in options:
            if not isinstance(value, str) or not value.startswith("--"):
                raise BackendError("invalid libVLC runtime option")
            if "\x00" in value or len(value.encode("utf-8")) > 256:
                raise BackendError("invalid libVLC runtime option")
            validated.append(value)
        return tuple(validated)

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
        changeset_api = self._optional_install("libvlc_get_changeset", ctypes.c_char_p, [])
        changeset = self.libvlc_get_changeset() if changeset_api else None
        return {
            "backend": "libVLC shared library",
            "version": version.decode("utf-8", "replace") if version else "unknown",
            "changeset": changeset.decode("utf-8", "replace") if changeset else "unknown",
            "plugin_path": os.environ.get("VLC_PLUGIN_PATH", "runtime default"),
            "network": "available",
            "hardware_decode": "delegated to installed libVLC modules",
            "player_process": "none",
            "runtime_options": " ".join(self.runtime_options) or "default",
        }

    def open(self, path: Path, subtitle: Path | None = None) -> None:
        self.open_source(path, subtitle=subtitle)

    def open_source(self, source: str | Path, subtitle: Path | None = None) -> None:
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
        if subtitle is not None:
            subtitle = subtitle.expanduser().resolve()
            if not subtitle.is_file():
                raise BackendError(f"subtitle file does not exist: {subtitle}")
            if not self._subtitle_option_api:
                raise BackendError("external subtitle loading is unavailable in this libVLC build")
            option = f":sub-file={subtitle}".encode("utf-8")
            self.libvlc_media_add_option(self.media, option)
        self.player = self.libvlc_media_player_new_from_media(self.media)
        if not self.player: self._state = PlaybackState.ERROR; raise BackendError("libVLC could not create media player")
        if sys.platform.startswith("linux"):
            self.libvlc_media_player_set_xwindow(self.player, self.widget.winfo_id())
        elif sys.platform.startswith("win"):
            self.libvlc_media_player_set_hwnd(self.player, ctypes.c_void_p(self.widget.winfo_id()))
        elif sys.platform == "darwin":
            self.libvlc_media_player_set_nsobject(self.player, ctypes.c_void_p(self.widget.winfo_id()))
        self._attach_events()
        self._state = PlaybackState.READY

    def add_external_subtitle(self, subtitle: Path) -> None:
        """Reopen the current source with a real libVLC subtitle option."""
        if self.path is None:
            raise BackendError("external subtitles require a local media source")
        position = self.position()
        was_playing = self.is_actively_playing()
        self.open_source(self.path, subtitle=subtitle)
        if was_playing:
            self.play()
            if position > 0:
                self.seek(position)

    def _attach_events(self) -> None:
        """Map libVLC lifecycle events to the backend state machine."""
        if not self._event_api or not self.player:
            return
        manager = self.libvlc_media_player_event_manager(self.player)
        if not manager:
            return
        self._event_manager = manager
        # Values are libvlc_event_e media-player constants.  Keeping this
        # optional lets older/minimal libVLC builds continue through polling.
        for event_type, state in LIBVLC_PLAYER_EVENT_STATES.items():
            def callback(_event, _user_data, state=state):
                self._state = state
                listener = self.on_event
                if listener is not None:
                    try:
                        listener(state)
                    except Exception:
                        # Backend callbacks must never bring down libVLC's
                        # worker thread because a UI listener failed.
                        pass
            callback_ref = self._event_callback_type(callback)
            if self.libvlc_event_attach(manager, event_type, callback_ref, None) == 0:
                self._event_callbacks.append((event_type, callback_ref))

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

    def next_frame(self) -> None:
        if not self._frame_step_api or not self.player:
            raise BackendError("frame stepping is unavailable in this libVLC build")
        if self.libvlc_media_player_next_frame(self.player) != 0:
            raise BackendError("libVLC rejected frame step")

    def chapter_count(self) -> int:
        if not self._chapter_api or not self.player:
            return 0
        title = int(self.libvlc_media_player_get_title(self.player))
        return max(0, int(self.libvlc_media_player_get_chapter_count(self.player, title)))

    def chapter(self) -> int:
        return int(self.libvlc_media_player_get_chapter(self.player)) if self._chapter_api and self.player else -1

    def set_chapter(self, chapter: int) -> None:
        if not self._chapter_api or not self.player:
            raise BackendError("chapter selection is unavailable in this libVLC build")
        if self.libvlc_media_player_set_chapter(self.player, int(chapter)) != 0:
            raise BackendError(f"libVLC rejected chapter {chapter}")

    def chapter_descriptors(self) -> tuple[ChapterDescriptor, ...]:
        return tuple(ChapterDescriptor(index, 0.0, f"Chapter {index + 1}")
                     for index in range(self.chapter_count()))

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
        if self._media_state_api and self.media:
            # libVLC media states: 6=Ended, 7=Error.  Opening/buffering are
            # deliberately left to the requested controller state.
            media_state = int(self.libvlc_media_get_state(self.media))
            if media_state == 7:
                self._state = PlaybackState.ERROR
            elif media_state == 6:
                self._state = PlaybackState.ENDED
        if self.player and self._state == PlaybackState.PLAYING and not self.libvlc_media_player_is_playing(self.player):
            if self.duration() and self.position() >= self.duration() - 0.2: self._state = PlaybackState.ENDED
        return self._state

    def media_state_code(self) -> int | None:
        """Return the raw libVLC media state when that API exists."""
        return int(self.libvlc_media_get_state(self.media)) if self._media_state_api and self.media else None

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

    def set_audio_delay(self, milliseconds: float) -> float:
        value = max(-5000.0, min(5000.0, float(milliseconds)))
        if not self._audio_delay_api or not self.player:
            raise BackendError("audio delay is unavailable in this libVLC build")
        if self.libvlc_audio_set_delay(self.player, int(value * 1000)) != 0:
            raise BackendError("libVLC rejected audio delay")
        return value

    def set_subtitle_delay(self, milliseconds: float) -> float:
        value = max(-5000.0, min(5000.0, float(milliseconds)))
        if not self._subtitle_delay_api or not self.player:
            raise BackendError("subtitle delay is unavailable in this libVLC build")
        if self.libvlc_video_set_spu_delay(self.player, int(value * 1000)) != 0:
            raise BackendError("libVLC rejected subtitle delay")
        return value

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

    def track_descriptors(self, kind: TrackKind) -> tuple[TrackDescriptor, ...]:
        getters = {
            TrackKind.VIDEO: self.video_track_descriptions,
            TrackKind.AUDIO: self.audio_track_descriptions,
            TrackKind.SUBTITLE: self.subtitle_track_descriptions,
        }
        return tuple(TrackDescriptor(identifier, kind, label or f"{kind.value} {identifier}")
                     for identifier, label in getters[TrackKind(kind)]())

    def audio_devices(self) -> tuple[AudioDeviceDescriptor, ...]:
        if not self._audio_device_api or not self.player:
            return ()
        pointer = self.libvlc_audio_output_device_enum(self.player)
        if not pointer:
            return ()
        devices = []
        current = pointer
        try:
            seen = 0
            while current and seen < 1024:
                item = current.contents
                identifier = (item.device or b"").decode("utf-8", "replace")
                label = (item.description or item.device or b"").decode("utf-8", "replace")
                if identifier:
                    devices.append(AudioDeviceDescriptor(identifier, label, "libVLC"))
                current = item.next
                seen += 1
        finally:
            self.libvlc_audio_output_device_list_release(pointer)
        return tuple(devices)

    def set_audio_device(self, identifier: str) -> None:
        if not self._audio_device_api or not self.player:
            raise BackendError("audio-device selection is unavailable in this libVLC build")
        self.libvlc_audio_output_device_set(self.player, None, str(identifier).encode("utf-8"))

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
        if self._event_manager and self._event_api:
            for event_type, callback_ref in self._event_callbacks:
                try:
                    self.libvlc_event_detach(self._event_manager, event_type, callback_ref, None)
                except (OSError, ctypes.ArgumentError):
                    pass
        self._event_callbacks.clear()
        self._event_manager = None
        if self.player: self.libvlc_media_player_stop(self.player); self.libvlc_media_player_release(self.player)
        if self.media: self.libvlc_media_release(self.media)
        self.player = self.media = None
        if self._native_temp is not None:
            try:
                self._native_temp.unlink(missing_ok=True)
            except OSError:
                pass
            self._native_temp = None

    def close(self):
        self.close_media()
        if self.instance: self.libvlc_release(self.instance)
        self.instance = None; self._state = PlaybackState.EMPTY


class LegacyCasuBackend(LibVLCBackend):
    """CASUNAT1/JSON compatibility path, intentionally separate from CASUNAT2."""

    def capabilities(self) -> dict[str, str]:
        values = super().capabilities()
        values.update({"backend_path": "CASUNAT1 envelope or JSON sidecar via libVLC",
                       "native_casu_payload": "no; verified compatibility extraction"})
        return values

    def open_casu(self, manifest_path: Path) -> None:
        manifest_path = manifest_path.expanduser().resolve()
        try:
            with manifest_path.open("rb") as handle:
                is_native = handle.read(8) == b"CASUNAT1"
        except OSError as exc:
            raise BackendError(f"could not read CASU file: {manifest_path}") from exc
        if is_native:
            try:
                container = read_native(manifest_path, verify_payload=True)
                suffix = Path(container.manifest.get("source", {}).get("filename", "media.bin")).suffix or ".bin"
                fd, temporary = tempfile.mkstemp(prefix="mpcasu-native-", suffix=suffix)
                os.close(fd)
                extracted = container.extract_payload(Path(temporary))
                # open_source closes any previous media; assign ownership only
                # after it succeeds so cleanup cannot remove the active file.
                self.open_source(extracted)
                self._native_temp = extracted
                self.path = manifest_path
                return
            except (NativeCasuError, OSError, BackendError) as exc:
                raise BackendError(f"invalid native CASU container: {exc}") from exc
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise BackendError(f"invalid CASU manifest: {manifest_path}") from exc
        errors = validate_manifest(manifest)
        if errors:
            raise BackendError(f"invalid CASU manifest: {errors[0]}")
        self.open(resolve_casu_source(manifest_path))


# Public compatibility alias retained for existing callers.  The actual
# native decoder is NativeCasuBackend in mpcasu_native_backend.py.
CasuBackend = LegacyCasuBackend


def os_path(path: Path) -> bytes:
    return str(path).encode(sys.getfilesystemencoding(), errors="surrogateescape")
