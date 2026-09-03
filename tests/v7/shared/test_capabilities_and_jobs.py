from pathlib import Path

import pytest

from v7.shared.capabilities import Capability, CapabilityManifest, CapabilityState
from v7.shared.jobs import OutputCollisionError, atomic_output
from v7.shared.lifecycle import CancelledOperation, CancellationSource, CancellationToken


def test_capability_manifest_is_explicit_immutable_and_generation_based():
    playback = Capability("playback.audio", CapabilityState.AVAILABLE)
    recording = Capability(
        "recording.microphone", CapabilityState.PERMISSION_REQUIRED,
        "Microphone permission is denied", "Grant microphone access in system settings",
    )
    manifest = CapabilityManifest({playback.capability_id: playback, recording.capability_id: recording})
    assert manifest.enabled("playback.audio")
    assert not manifest.enabled("recording.microphone")
    with pytest.raises(KeyError):
        manifest.enabled("undeclared")
    updated = manifest.replace(Capability("recording.microphone", CapabilityState.AVAILABLE))
    assert updated.generation == 1 and updated.enabled("recording.microphone")
    assert not manifest.enabled("recording.microphone")


def test_unavailable_capability_requires_explanation():
    with pytest.raises(ValueError):
        Capability("playback.video", CapabilityState.UNAVAILABLE)
    with pytest.raises(ValueError):
        Capability("playback.video", CapabilityState.AVAILABLE, "not really")


def test_atomic_output_publishes_only_complete_content(tmp_path: Path):
    target = tmp_path / "result.bin"
    result = atomic_output(target, lambda stream, _token: stream.write(b"complete"), cancellation=CancellationToken())
    assert result.path == target and result.size == 8 and target.read_bytes() == b"complete"
    assert not list(tmp_path.glob("*.partial"))


def test_atomic_output_cleans_cancelled_and_failed_partial_files(tmp_path: Path):
    target = tmp_path / "result.bin"
    source = CancellationSource()

    def cancelled(stream, cancellation):
        stream.write(b"partial")
        source.cancel()
        cancellation.raise_if_cancelled()

    with pytest.raises(CancelledOperation):
        atomic_output(target, cancelled, cancellation=source.token)
    assert not target.exists() and not list(tmp_path.glob("*.partial"))

    def failed(stream, _cancellation):
        stream.write(b"partial")
        raise RuntimeError("encoder failed")

    with pytest.raises(RuntimeError):
        atomic_output(target, failed, cancellation=CancellationToken())
    assert not target.exists() and not list(tmp_path.glob("*.partial"))


def test_atomic_output_collision_is_non_destructive(tmp_path: Path):
    target = tmp_path / "result.bin"
    target.write_bytes(b"old")
    with pytest.raises(OutputCollisionError):
        atomic_output(target, lambda stream, _token: stream.write(b"new"), cancellation=CancellationToken())
    assert target.read_bytes() == b"old"
