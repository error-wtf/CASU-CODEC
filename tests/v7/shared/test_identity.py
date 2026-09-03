"""Contract tests for V7-CORE-SHARED-001 identity semantics."""

from dataclasses import FrozenInstanceError

import pytest

from v7.shared.core.identity import IdentityValidationError, MediaIdentity
from v7.shared.queue.model import QueueOccurrence


MEDIA_ID = "med_0123456789abcdef"
OTHER_MEDIA_ID = "med_fedcba9876543210"
OCCURRENCE_ID = "occ_0123456789abcdef"


def test_req_core_id_001_media_identity_is_value_comparable_and_immutable() -> None:
    first = MediaIdentity(MEDIA_ID, "local", "file:///music/example.mp3")
    equivalent = MediaIdentity(MEDIA_ID, "local", "file:///music/example.mp3")

    assert first == equivalent
    assert hash(first) == hash(equivalent)

    with pytest.raises(FrozenInstanceError):
        first.media_id = OTHER_MEDIA_ID  # type: ignore[misc]


@pytest.mark.parametrize(
    ("media_id", "identity_kind", "canonical_key"),
    [
        ("bad-id", "local", "file:///music/example.mp3"),
        (MEDIA_ID, "unknown", "file:///music/example.mp3"),
        (MEDIA_ID, "local", ""),
        (MEDIA_ID, "local", "x" * 4097),
    ],
)
def test_req_core_id_001_rejects_invalid_identity_fields(
    media_id: str, identity_kind: str, canonical_key: str
) -> None:
    with pytest.raises(IdentityValidationError):
        MediaIdentity(media_id, identity_kind, canonical_key)


def test_req_core_id_001_factory_generates_schema_compatible_identity() -> None:
    identity = MediaIdentity.create("provider", "youtube:video:abc123")

    assert identity.media_id.startswith("med_")
    assert len(identity.media_id) >= 20
    assert identity.identity_kind == "provider"
    assert identity.canonical_key == "youtube:video:abc123"


def test_req_core_id_002_each_queue_insertion_gets_a_distinct_immutable_id() -> None:
    media = MediaIdentity(MEDIA_ID, "local", "file:///music/example.mp3")

    first = QueueOccurrence.create(media)
    second = QueueOccurrence.create(media)

    assert first.media == second.media
    assert first.occurrence_id != second.occurrence_id
    assert first.occurrence_id.startswith("occ_")

    with pytest.raises(FrozenInstanceError):
        first.occurrence_id = OCCURRENCE_ID  # type: ignore[misc]
