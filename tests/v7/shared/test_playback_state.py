import threading

import pytest

from v7.shared.core.errors import ErrorCode, StructuredError
from v7.shared.playback import PlaybackOwnerError, PlaybackState, PlaybackStateMachine


def test_open_ready_play_pause_resume_stop_sequence() -> None:
    machine = PlaybackStateMachine()
    generation = machine.begin_open()
    assert machine.state is PlaybackState.LOADING
    assert machine.backend_ready(generation)
    assert machine.command_succeeded(generation, "play")
    assert machine.state is PlaybackState.PLAYING
    assert machine.command_succeeded(generation, "pause")
    assert machine.state is PlaybackState.PAUSED
    assert machine.command_succeeded(generation, "resume")
    assert machine.command_succeeded(generation, "stop")
    assert machine.state is PlaybackState.STOPPED
    assert machine.command_succeeded(generation, "stop")


def test_state_is_not_published_when_backend_command_fails() -> None:
    machine = PlaybackStateMachine()
    generation = machine.begin_open()
    machine.backend_ready(generation)
    assert not machine.command_failed(generation, "play")
    assert machine.state is PlaybackState.READY


def test_replacement_invalidates_late_callbacks() -> None:
    machine = PlaybackStateMachine()
    old = machine.begin_open()
    new = machine.begin_open()
    assert not machine.backend_ready(old)
    assert machine.backend_ready(new)
    assert machine.state is PlaybackState.READY


def test_failure_retains_redacted_typed_cause() -> None:
    machine = PlaybackStateMachine()
    generation = machine.begin_open()
    error = StructuredError.for_code(
        ErrorCode.DECODER_FAILURE,
        "playback",
        "open",
        "Cannot decode",
        safe_detail="token=secret",
    )
    assert machine.fail(generation, error)
    assert machine.state is PlaybackState.FAILED
    assert machine.error is error
    assert "secret" not in (machine.error.safe_detail or "")


def test_ended_requires_current_generation_and_active_state() -> None:
    machine = PlaybackStateMachine()
    generation = machine.begin_open()
    machine.backend_ready(generation)
    assert not machine.ended(generation)
    machine.command_succeeded(generation, "play")
    assert machine.ended(generation)
    assert machine.state is PlaybackState.ENDED


def test_close_is_idempotent_terminal_and_suppresses_callbacks() -> None:
    machine = PlaybackStateMachine()
    generation = machine.begin_open()
    machine.close()
    machine.close()
    assert machine.state is PlaybackState.CLOSED
    assert not machine.backend_ready(generation)
    with pytest.raises(PlaybackOwnerError):
        machine.begin_open()


def test_owner_thread_is_enforced() -> None:
    machine = PlaybackStateMachine()
    errors: list[Exception] = []
    thread = threading.Thread(target=lambda: _capture(errors, machine.begin_open))
    thread.start()
    thread.join()
    assert isinstance(errors[0], PlaybackOwnerError)


def _capture(errors: list[Exception], callback) -> None:
    try:
        callback()
    except Exception as error:
        errors.append(error)
