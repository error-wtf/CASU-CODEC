"""Generation-safe recording/finalization state authority."""

from __future__ import annotations

from enum import Enum
import threading

from .core.errors import ErrorCode, StructuredError
from .lifecycle import GenerationGate


class RecordingState(str, Enum):
    IDLE = "idle"
    STARTING = "starting"
    RECORDING = "recording"
    STOPPING = "stopping"
    FINALIZING = "finalizing"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RecordingTransitionError(RuntimeError):
    pass


class RecordingStateMachine:
    def __init__(self) -> None:
        self._owner = threading.get_ident()
        self._gate = GenerationGate()
        self._generation = 0
        self._state = RecordingState.IDLE
        self._error: StructuredError | None = None

    @property
    def state(self) -> RecordingState:
        return self._state

    @property
    def error(self) -> StructuredError | None:
        return self._error

    def begin_start(self) -> int:
        self._require_owner()
        if self._state not in {RecordingState.IDLE, RecordingState.COMPLETE, RecordingState.FAILED, RecordingState.CANCELLED}:
            raise RecordingTransitionError(f"cannot start from {self._state.value}")
        self._generation = self._gate.begin()
        self._state = RecordingState.STARTING
        self._error = None
        return self._generation

    def started(self, generation: int) -> bool:
        return self._transition(generation, {RecordingState.STARTING}, RecordingState.RECORDING)

    def begin_stop(self, generation: int) -> bool:
        self._require_owner()
        if self._state is RecordingState.STOPPING and self._gate.is_current(generation):
            return True
        return self._transition(generation, {RecordingState.RECORDING}, RecordingState.STOPPING)

    def backend_drained(self, generation: int) -> bool:
        self._require_owner()
        if self._state in {RecordingState.FINALIZING, RecordingState.COMPLETE} and self._gate.is_current(generation):
            return False
        return self._transition(generation, {RecordingState.STOPPING}, RecordingState.FINALIZING)

    def validation_complete(self, generation: int, *, valid: bool) -> bool:
        self._require_owner()
        if type(valid) is not bool:
            raise TypeError("valid must be boolean")
        if valid:
            return self._transition(generation, {RecordingState.FINALIZING}, RecordingState.COMPLETE)
        error = StructuredError.for_code(
            ErrorCode.OUTPUT_FINALIZATION_FAILURE,
            "recording", "validate", "Finalized recording is invalid",
        )
        self.fail(generation, error)
        return False

    def cancel(self, generation: int) -> bool:
        self._require_owner()
        if not self._gate.is_current(generation):
            return False
        if self._state in {RecordingState.COMPLETE, RecordingState.FAILED, RecordingState.CANCELLED, RecordingState.IDLE}:
            return False
        self._state = RecordingState.CANCELLED
        self._gate.invalidate()
        return True

    def fail(self, generation: int, error: StructuredError) -> bool:
        self._require_owner()
        if not isinstance(error, StructuredError):
            raise TypeError("error must be StructuredError")

        def publish() -> bool:
            self._state = RecordingState.FAILED
            self._error = error
            return True

        return bool(self._gate.publish(generation, publish))

    def _transition(self, generation: int, allowed: set[RecordingState], target: RecordingState) -> bool:
        self._require_owner()

        def publish() -> bool:
            if self._state not in allowed:
                raise RecordingTransitionError(
                    f"cannot transition from {self._state.value} to {target.value}"
                )
            self._state = target
            return True

        return bool(self._gate.publish(generation, publish))

    def _require_owner(self) -> None:
        if threading.get_ident() != self._owner:
            raise RecordingTransitionError("recording mutation must run on owner thread")
