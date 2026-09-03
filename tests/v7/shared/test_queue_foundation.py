"""Queue model and persistence tests for V7-CORE-SHARED-001."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from v7.shared.core.identity import MediaIdentity
from v7.shared.queue.model import (
    MAX_QUEUE_OCCURRENCES,
    OccurrenceNotFoundError,
    QueueOccurrence,
    QueueState,
    QueueStateValidationError,
)
from v7.shared.queue.serialization import (
    QueueStateDecodeError,
    deserialize_queue_state,
    serialize_queue_state,
)


MEDIA_A = MediaIdentity(
    "med_0123456789abcdef", "local", "file:///music/example.mp3"
)
MEDIA_B = MediaIdentity(
    "med_fedcba9876543210", "provider", "youtube:video:example"
)


def _prep_root() -> Path:
    configured = os.environ.get("PREP_ROOT")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3].parent / "ALL_RELEASE_V7"


def _fixture(name: str) -> bytes:
    configured = os.environ.get("PREP_ROOT")
    if configured:
        return (Path(configured) / "contracts" / "fixtures" / name).read_bytes()
    return (Path(__file__).resolve().parents[1] / "fixtures" / name).read_bytes()


def _occurrence(
    occurrence_id: str,
    media: MediaIdentity = MEDIA_A,
    insertion_class: str = "permanent",
) -> QueueOccurrence:
    return QueueOccurrence(occurrence_id, media, insertion_class, None)


def test_req_core_queue_001_duplicate_media_are_distinct_occurrences() -> None:
    state = QueueState.empty().append(MEDIA_A).append(MEDIA_A)

    assert len(state.occurrences) == 2
    assert state.occurrences[0].media == state.occurrences[1].media
    assert state.occurrences[0].occurrence_id != state.occurrences[1].occurrence_id


def test_req_core_queue_001_remove_and_move_target_occurrence_identity() -> None:
    one = _occurrence("occ_0000000000000001")
    two = _occurrence("occ_0000000000000002")
    three = _occurrence("occ_0000000000000003", MEDIA_B)
    state = QueueState(1, 0, (one, two, three), two.occurrence_id, ())

    moved = state.move(three.occurrence_id, 0)
    assert [item.occurrence_id for item in moved.occurrences] == [
        three.occurrence_id,
        one.occurrence_id,
        two.occurrence_id,
    ]

    removed = moved.remove(one.occurrence_id)
    assert [item.occurrence_id for item in removed.occurrences] == [
        three.occurrence_id,
        two.occurrence_id,
    ]
    assert removed.current_occurrence_id == two.occurrence_id

    with pytest.raises(OccurrenceNotFoundError):
        removed.remove("occ_9999999999999999")


def test_req_core_queue_002_empty_and_current_selection_semantics() -> None:
    empty = QueueState.empty()
    assert empty.occurrences == ()
    assert empty.current_occurrence_id is None

    occurrence = _occurrence("occ_0000000000000001")
    state = QueueState(1, 0, (occurrence,), None, ())
    selected = state.with_current(occurrence.occurrence_id)
    assert selected.current_occurrence_id == occurrence.occurrence_id
    assert selected.with_current(None).current_occurrence_id is None

    with pytest.raises(OccurrenceNotFoundError):
        state.with_current("occ_9999999999999999")


def test_req_core_ser_001_valid_fixtures_round_trip_deterministically() -> None:
    for name in (
        "queue-foundation-valid-empty.json",
        "queue-foundation-valid-duplicates.json",
    ):
        state = deserialize_queue_state(_fixture(name))
        first = serialize_queue_state(state)
        second = serialize_queue_state(deserialize_queue_state(first))
        assert first == second


def test_req_core_ser_001_unicode_round_trip_is_utf8_and_not_ascii_escaped() -> None:
    occurrence = QueueOccurrence(
        "occ_0000000000000001",
        MediaIdentity(
            "med_0000000000000001",
            "local",
            "file:///Musik/Über den Wolken 🎵.mp3",
        ),
        "permanent",
        "Über den Wolken 🎵",
    )
    encoded = serialize_queue_state(QueueState(1, 7, (occurrence,), None, ()))

    assert "Über den Wolken 🎵" in encoded.decode("utf-8")
    assert deserialize_queue_state(encoded).occurrences[0] == occurrence


def test_req_core_ser_001_accepts_10000_and_rejects_10001_occurrences() -> None:
    occurrences = tuple(
        _occurrence(f"occ_{index:016x}") for index in range(MAX_QUEUE_OCCURRENCES)
    )
    state = QueueState(1, 0, occurrences, None, ())
    assert len(deserialize_queue_state(serialize_queue_state(state)).occurrences) == 10_000

    with pytest.raises(QueueStateValidationError):
        QueueState(1, 0, occurrences + (_occurrence("occ_ffffffffffffffff"),), None, ())


@pytest.mark.parametrize(
    "name",
    [
        "queue-foundation-invalid-duplicate-occurrence.json",
        "queue-foundation-invalid-current.json",
        "queue-foundation-invalid-play-next.json",
    ],
)
def test_req_core_ser_002_rejects_prepared_negative_fixtures(name: str) -> None:
    with pytest.raises(QueueStateDecodeError):
        deserialize_queue_state(_fixture(name))


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        (b"{not-json", "MALFORMED_JSON"),
        (
            json.dumps(
                {
                    "schema_version": 2,
                    "revision": 0,
                    "occurrences": [],
                    "current_occurrence_id": None,
                    "play_next_ids": [],
                }
            ).encode(),
            "UNSUPPORTED_SCHEMA_VERSION",
        ),
        (
            json.dumps(
                {
                    "schema_version": 1,
                    "revision": 0,
                    "occurrences": [],
                    "current_occurrence_id": None,
                    "play_next_ids": [],
                    "surprise": True,
                }
            ).encode(),
            "UNKNOWN_PROPERTY",
        ),
    ],
)
def test_req_core_ser_002_rejects_malformed_future_and_unknown_properties(
    payload: bytes, expected_code: str
) -> None:
    with pytest.raises(QueueStateDecodeError) as raised:
        deserialize_queue_state(payload)
    assert raised.value.code == expected_code


def test_req_core_ser_002_decode_failure_cannot_mutate_previous_state() -> None:
    previous = QueueState.empty().append(MEDIA_A)
    snapshot = serialize_queue_state(previous)

    with pytest.raises(QueueStateDecodeError):
        deserialize_queue_state(_fixture("queue-foundation-invalid-current.json"))

    assert serialize_queue_state(previous) == snapshot


def test_req_core_queue_001_play_next_membership_tracks_mutations() -> None:
    state = QueueState.empty().append(MEDIA_A, insertion_class="play_next")
    occurrence_id = state.occurrences[0].occurrence_id
    assert state.play_next_ids == (occurrence_id,)

    assert state.remove(occurrence_id) == QueueState(1, 2, (), None, ())
