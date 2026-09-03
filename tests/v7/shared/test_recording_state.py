import pytest

from v7.shared.core.errors import ErrorCode, StructuredError
from v7.shared.recording import RecordingState, RecordingStateMachine, RecordingTransitionError


def test_successful_recording_requires_finalize_and_validation() -> None:
    machine = RecordingStateMachine()
    generation = machine.begin_start()
    assert machine.started(generation)
    assert machine.begin_stop(generation)
    assert machine.backend_drained(generation)
    assert not machine.validation_complete(generation, valid=False)
    assert machine.state is RecordingState.FAILED

    generation = machine.begin_start()
    machine.started(generation)
    machine.begin_stop(generation)
    machine.backend_drained(generation)
    assert machine.validation_complete(generation, valid=True)
    assert machine.state is RecordingState.COMPLETE


def test_stop_and_finalize_callbacks_are_idempotent() -> None:
    machine = RecordingStateMachine()
    generation = machine.begin_start()
    machine.started(generation)
    assert machine.begin_stop(generation)
    assert machine.begin_stop(generation)
    assert machine.backend_drained(generation)
    assert not machine.backend_drained(generation)


def test_cancel_invalidates_late_backend_completion() -> None:
    machine = RecordingStateMachine()
    generation = machine.begin_start()
    machine.cancel(generation)
    assert machine.state is RecordingState.CANCELLED
    assert not machine.started(generation)


def test_failure_is_typed_and_retained() -> None:
    machine = RecordingStateMachine()
    generation = machine.begin_start()
    error = StructuredError.for_code(
        ErrorCode.OUTPUT_FINALIZATION_FAILURE,
        "recording", "finalize", "Could not finalize",
    )
    assert machine.fail(generation, error)
    assert machine.error == error
    assert machine.state is RecordingState.FAILED


def test_invalid_transition_is_rejected() -> None:
    machine = RecordingStateMachine()
    generation = machine.begin_start()
    with pytest.raises(RecordingTransitionError):
        machine.begin_stop(generation)


def test_new_start_replaces_terminal_generation_only() -> None:
    machine = RecordingStateMachine()
    first = machine.begin_start()
    with pytest.raises(RecordingTransitionError):
        machine.begin_start()
    machine.cancel(first)
    second = machine.begin_start()
    assert second > first
