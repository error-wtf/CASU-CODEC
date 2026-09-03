"""Generation, cancellation and ownership foundation tests."""

import threading

import pytest

from v7.shared.lifecycle import (
    CancelledOperation,
    CancellationSource,
    GenerationGate,
    OwnerClosedError,
)


def test_new_generation_invalidates_all_older_callbacks() -> None:
    gate = GenerationGate()
    first = gate.begin()
    second = gate.begin()
    assert not gate.is_current(first)
    assert gate.is_current(second)
    assert gate.publish(first, lambda: "stale") is None
    assert gate.publish(second, lambda: "current") == "current"


def test_close_rejects_new_work_and_invalidates_current_generation() -> None:
    gate = GenerationGate()
    active = gate.begin()
    gate.close()
    assert not gate.is_current(active)
    assert gate.publish(active, lambda: pytest.fail("must not publish")) is None
    gate.close()
    with pytest.raises(OwnerClosedError):
        gate.begin()


def test_cancellation_is_idempotent_and_callbacks_run_once() -> None:
    source = CancellationSource()
    observed: list[str] = []
    source.token.add_callback(lambda: observed.append("cancelled"))
    assert source.cancel() is True
    assert source.cancel() is False
    assert observed == ["cancelled"]
    assert source.token.cancelled
    with pytest.raises(CancelledOperation):
        source.token.raise_if_cancelled()


def test_callback_registered_after_cancel_runs_immediately() -> None:
    source = CancellationSource()
    source.cancel()
    observed: list[str] = []
    source.token.add_callback(lambda: observed.append("late"))
    assert observed == ["late"]


def test_generation_gate_is_thread_safe_under_replacement() -> None:
    gate = GenerationGate()
    generations: list[int] = []

    def replace() -> None:
        generations.append(gate.begin())

    threads = [threading.Thread(target=replace) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(generations) == list(range(1, 21))
    assert gate.current_generation == 20


def test_cancel_callback_failure_does_not_skip_remaining_cleanup() -> None:
    source = CancellationSource()
    observed: list[str] = []
    source.token.add_callback(lambda: observed.append("first"))

    def fail() -> None:
        raise RuntimeError("cleanup failure")

    source.token.add_callback(fail)
    source.token.add_callback(lambda: observed.append("last"))
    failures = source.cancel()
    assert failures == ("cleanup failure",)
    assert observed == ["first", "last"]
