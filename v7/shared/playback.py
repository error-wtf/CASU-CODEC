"""Owner-thread, generation-tagged playback state authority."""

from __future__ import annotations

from enum import Enum
import threading
import time

from .core.errors import StructuredError
from .core.identity import MediaIdentity
from .lifecycle import GenerationGate, OwnerClosedError
from .source_location import SourceLocation


class PlaybackDescriptorExpiredError(RuntimeError):
    pass


class PlaybackDescriptor:
    """Transient backend input; deliberately not persistent media identity."""

    __slots__ = ("identity", "location", "generation", "expires_at_ms", "headers")

    def __init__(self, identity: MediaIdentity, location: SourceLocation, generation: int,
                 *, expires_at_ms: int | None = None,
                 headers: dict[str, str] | None = None) -> None:
        if not isinstance(identity, MediaIdentity):
            raise TypeError("identity must be MediaIdentity")
        if not isinstance(location, SourceLocation):
            raise TypeError("location must be SourceLocation")
        if type(generation) is not int or generation < 0:
            raise ValueError("generation must be non-negative")
        if expires_at_ms is not None and (type(expires_at_ms) is not int or expires_at_ms < 0):
            raise ValueError("expires_at_ms must be non-negative")
        copied = dict(headers or {})
        if len(copied) > 32 or any(
            not isinstance(key, str) or not key or len(key) > 128
            or not isinstance(value, str) or len(value) > 8192
            or "\n" in key or "\r" in key or "\n" in value or "\r" in value
            for key, value in copied.items()
        ):
            raise ValueError("invalid transport headers")
        self.identity = identity
        self.location = location
        self.generation = generation
        self.expires_at_ms = expires_at_ms
        self.headers = copied

    def require_usable(self, generation: int, *, now_ms: int | None = None) -> None:
        if generation != self.generation:
            raise PlaybackDescriptorExpiredError("descriptor belongs to an obsolete generation")
        clock = int(time.time() * 1000) if now_ms is None else now_ms
        if type(clock) is not int or clock < 0:
            raise ValueError("now_ms must be non-negative")
        if self.expires_at_ms is not None and clock >= self.expires_at_ms:
            raise PlaybackDescriptorExpiredError("transport location has expired")

    def __repr__(self) -> str:
        return (f"PlaybackDescriptor(identity={self.identity!r}, location={self.location!r}, "
                f"generation={self.generation}, expires_at_ms={self.expires_at_ms}, "
                "headers=<redacted>)")


class PlaybackState(str, Enum):
    EMPTY = "empty"
    LOADING = "loading"
    READY = "ready"
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"
    ENDED = "ended"
    FAILED = "failed"
    CLOSING = "closing"
    CLOSED = "closed"


class PlaybackOwnerError(RuntimeError):
    pass


class PlaybackTransitionError(RuntimeError):
    pass


_COMMAND_TRANSITIONS = {
    "play": ({PlaybackState.READY, PlaybackState.STOPPED, PlaybackState.ENDED}, PlaybackState.PLAYING),
    "pause": ({PlaybackState.PLAYING}, PlaybackState.PAUSED),
    "resume": ({PlaybackState.PAUSED}, PlaybackState.PLAYING),
    "stop": ({PlaybackState.READY, PlaybackState.PLAYING, PlaybackState.PAUSED, PlaybackState.STOPPED, PlaybackState.ENDED}, PlaybackState.STOPPED),
}


class PlaybackStateMachine:
    def __init__(self) -> None:
        self._owner = threading.get_ident()
        self._gate = GenerationGate()
        self._state = PlaybackState.EMPTY
        self._generation = 0
        self._error: StructuredError | None = None

    @property
    def state(self) -> PlaybackState:
        return self._state

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def error(self) -> StructuredError | None:
        return self._error

    def begin_open(self) -> int:
        self._require_owner()
        if self._state in {PlaybackState.CLOSING, PlaybackState.CLOSED}:
            raise PlaybackOwnerError("playback owner is closed")
        try:
            self._generation = self._gate.begin()
        except OwnerClosedError as error:
            raise PlaybackOwnerError(str(error)) from error
        self._error = None
        self._state = PlaybackState.LOADING
        return self._generation

    def backend_ready(self, generation: int) -> bool:
        self._require_owner()
        return bool(self._gate.publish(generation, self._publish_ready))

    def _publish_ready(self) -> bool:
        if self._state is not PlaybackState.LOADING:
            return False
        self._state = PlaybackState.READY
        return True

    def command_succeeded(self, generation: int, command: str) -> bool:
        self._require_owner()
        transition = _COMMAND_TRANSITIONS.get(command)
        if transition is None:
            raise ValueError(f"unknown playback command: {command}")

        def publish() -> bool:
            allowed, target = transition
            if self._state not in allowed:
                raise PlaybackTransitionError(
                    f"{command} is invalid from {self._state.value}"
                )
            self._state = target
            return True

        return bool(self._gate.publish(generation, publish))

    def command_failed(self, generation: int, command: str) -> bool:
        """A failed backend command intentionally publishes no state change."""
        self._require_owner()
        if command not in _COMMAND_TRANSITIONS:
            raise ValueError(f"unknown playback command: {command}")
        return False if self._gate.is_current(generation) else False

    def ended(self, generation: int) -> bool:
        self._require_owner()

        def publish() -> bool:
            if self._state not in {PlaybackState.PLAYING, PlaybackState.PAUSED}:
                return False
            self._state = PlaybackState.ENDED
            return True

        return bool(self._gate.publish(generation, publish))

    def fail(self, generation: int, error: StructuredError) -> bool:
        self._require_owner()
        if not isinstance(error, StructuredError):
            raise TypeError("error must be StructuredError")

        def publish() -> bool:
            if self._state in {PlaybackState.CLOSING, PlaybackState.CLOSED}:
                return False
            self._state = PlaybackState.FAILED
            self._error = error
            return True

        return bool(self._gate.publish(generation, publish))

    def close(self) -> None:
        self._require_owner()
        if self._state is PlaybackState.CLOSED:
            return
        self._state = PlaybackState.CLOSING
        self._gate.close()
        self._state = PlaybackState.CLOSED

    def _require_owner(self) -> None:
        if threading.get_ident() != self._owner:
            raise PlaybackOwnerError("playback state mutation must run on owner thread")
