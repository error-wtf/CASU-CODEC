"""Atomic queue persistence tests for the V7 shared core."""

from pathlib import Path

import pytest

from v7.shared.core.identity import MediaIdentity
from v7.shared.queue.model import QueueState
from v7.shared.queue.persistence import (
    AtomicQueueStateStore,
    QueuePersistenceError,
)


MEDIA = MediaIdentity("med_0123456789abcdef", "local", "file:///music/a.mp3")


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "state" / "queue.json"
    state = QueueState.empty().append(MEDIA).with_current(None)
    store = AtomicQueueStateStore(path)

    store.save(state)
    loaded = store.load()

    assert loaded.state == state
    assert loaded.source == "primary"
    assert path.stat().st_mode & 0o077 == 0


def test_second_save_retains_one_valid_recovery_copy(tmp_path: Path) -> None:
    path = tmp_path / "queue.json"
    store = AtomicQueueStateStore(path)
    first = QueueState.empty().append(MEDIA)
    second = first.append(MEDIA)

    store.save(first)
    store.save(second)

    assert store.load().state == second
    path.write_bytes(b"corrupt")
    recovered = store.load()
    assert recovered.state == first
    assert recovered.source == "recovery"
    assert recovered.primary_error is not None


def test_corrupt_primary_without_recovery_returns_safe_default(tmp_path: Path) -> None:
    path = tmp_path / "queue.json"
    path.write_bytes(b"not-json")
    result = AtomicQueueStateStore(path).load()
    assert result.state == QueueState.empty()
    assert result.source == "default"
    assert result.primary_error is not None


def test_missing_state_returns_safe_default(tmp_path: Path) -> None:
    result = AtomicQueueStateStore(tmp_path / "missing.json").load()
    assert result.state == QueueState.empty()
    assert result.source == "default"
    assert result.primary_error is None


def test_oversize_document_is_rejected_before_json_decode(tmp_path: Path) -> None:
    path = tmp_path / "queue.json"
    path.write_bytes(b"x" * 33)
    result = AtomicQueueStateStore(path, max_document_bytes=32).load()
    assert result.source == "default"
    assert result.primary_error is not None
    assert result.primary_error.code == "QUEUE_STATE_OVERSIZE"


def test_failed_primary_replace_leaves_previous_state(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "queue.json"
    store = AtomicQueueStateStore(path)
    first = QueueState.empty().append(MEDIA)
    store.save(first)
    real_replace = __import__("os").replace

    def fail_primary(source, destination):
        if Path(destination) == path:
            raise OSError("injected replace failure")
        return real_replace(source, destination)

    monkeypatch.setattr("v7.shared.queue.persistence.os.replace", fail_primary)
    with pytest.raises(QueuePersistenceError) as raised:
        store.save(first.append(MEDIA))
    assert raised.value.code == "QUEUE_STATE_WRITE_FAILED"
    assert store.load().state == first
    assert not list(tmp_path.glob(".queue.json.*.tmp"))


def test_save_rejects_document_above_configured_limit(tmp_path: Path) -> None:
    store = AtomicQueueStateStore(tmp_path / "queue.json", max_document_bytes=32)
    with pytest.raises(QueuePersistenceError) as raised:
        store.save(QueueState.empty())
    assert raised.value.code == "QUEUE_STATE_OVERSIZE"
