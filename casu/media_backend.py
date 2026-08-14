from __future__ import annotations

import abc
from pathlib import Path
from typing import Any, Protocol

from casu.media import AudioDeviceDescriptor, ChapterDescriptor, TrackDescriptor
from casu.native_v2.audio import AudioBlock
from casu.strict.canonical import CanonicalFrame


class MediaBackend(abc.ABC):
    """Abstract interface that every playback backend must implement.

    MPCASU's UI and PlaybackController interact with backends exclusively
    through this interface.  No caller should import libVLC or CASU internals
    directly.
    """

    @abc.abstractmethod
    def open_source(self, source: str | Path, subtitle: Path | None = None) -> None:
        """Open a media source and prepare it for playback."""

    @abc.abstractmethod
    def play(self) -> None:
        """Start or resume playback."""

    @abc.abstractmethod
    def pause(self) -> None:
        """Pause active playback."""

    @abc.abstractmethod
    def resume(self) -> None:
        """Resume from paused state."""

    @abc.abstractmethod
    def stop(self) -> None:
        """Stop playback and reset position."""

    @abc.abstractmethod
    def seek(self, seconds: float) -> None:
        """Seek to a given time in seconds."""

    @abc.abstractmethod
    def close(self) -> None:
        """Release all resources held by this backend."""

    @property
    @abc.abstractmethod
    def state(self) -> Any:
        """Return the current playback state enum value."""

    @abc.abstractmethod
    def position(self) -> float:
        """Current playback position in seconds."""

    @abc.abstractmethod
    def duration(self) -> float:
        """Total media duration in seconds."""

    @abc.abstractmethod
    def volume(self) -> int:
        """Current volume level (0-100)."""

    @abc.abstractmethod
    def set_volume(self, value: int) -> None:
        """Set volume (0-100)."""

    @abc.abstractmethod
    def mute(self, muted: bool) -> None:
        """Mute or unmute audio."""

    @abc.abstractmethod
    def is_muted(self) -> bool:
        """Return True if audio is muted."""

    @abc.abstractmethod
    def rate(self) -> float:
        """Current playback rate (1.0 = normal)."""

    @abc.abstractmethod
    def set_rate(self, value: float) -> None:
        """Set playback rate."""

    @abc.abstractmethod
    def audio_tracks(self) -> tuple[TrackDescriptor, ...]:
        """Return available audio tracks."""

    @abc.abstractmethod
    def video_tracks(self) -> tuple[TrackDescriptor, ...]:
        """Return available video tracks."""

    @abc.abstractmethod
    def subtitle_tracks(self) -> tuple[TrackDescriptor, ...]:
        """Return available subtitle tracks."""

    @abc.abstractmethod
    def set_audio_track(self, identifier: int) -> None:
        """Select an audio track by identifier."""

    @abc.abstractmethod
    def set_subtitle_track(self, identifier: int) -> None:
        """Select a subtitle track by identifier."""

    @abc.abstractmethod
    def chapters(self) -> tuple[ChapterDescriptor, ...]:
        """Return chapter descriptors."""

    @abc.abstractmethod
    def set_chapter(self, identifier: int) -> None:
        """Jump to a chapter."""

    @abc.abstractmethod
    def audio_devices(self) -> tuple[AudioDeviceDescriptor, ...]:
        """Return available audio output devices."""

    @abc.abstractmethod
    def set_audio_device(self, identifier: str) -> None:
        """Select an audio output device."""

    @abc.abstractmethod
    def set_audio_delay(self, seconds: float) -> None:
        """Set audio delay in seconds."""

    @abc.abstractmethod
    def set_subtitle_delay(self, seconds: float) -> None:
        """Set subtitle delay in seconds."""

    @abc.abstractmethod
    def load_external_subtitle(self, path: Path) -> None:
        """Load an external subtitle file."""

    @abc.abstractmethod
    def supports(source: str | Path) -> bool:
        """Return True if this backend can handle the given source."""
        ...


class VideoSink(Protocol):
    """Protocol for video output sinks (Tk canvas, Qt widget, null)."""

    def present(self, frame: CanonicalFrame, pts_seconds: float) -> None: ...
    def present_cover(self, data: bytes, media_type: str) -> None: ...
    def present_subtitle_rgba(self, rgba: Any, pts_seconds: float) -> None: ...
    def clear_subtitle(self) -> None: ...
    def invalidate(self) -> None: ...
    def close(self) -> None: ...


class AudioSink(Protocol):
    """Protocol for audio output sinks (PulseAudio, null, file)."""

    def write(self, block: AudioBlock) -> None: ...
    def flush(self) -> None: ...
    def reset_format(self) -> None: ...
    def close(self) -> None: ...
    def set_volume(self, value: int) -> None: ...
    def set_mute(self, muted: bool) -> None: ...
    def latency_seconds(self) -> float | None: ...
