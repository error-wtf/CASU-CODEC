"""Contract tests for the V7 persistent MediaItem envelope."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from v7.shared.core.errors import StructuredError
from v7.shared.core.identity import MediaIdentity
from v7.shared.core.media_item import (
    MediaItem,
    MediaItemDecodeError,
    MediaItemValidationError,
    deserialize_media_item,
    serialize_media_item,
)


def _item() -> MediaItem:
    return MediaItem(
        identity=MediaIdentity(
            "med_0123456789abcdef", "provider", "youtube:video:abc"
        ),
        kind="youtube",
        original_source="https://www.youtube.com/watch?v=abc",
        title="Grüße 🎵",
        artist="Artist",
        duration_ms=1234,
        provider="youtube",
        provider_id="abc",
        availability="available",
        metadata={"nested": {"quality": "best"}, "numbers": [1, 2]},
        diagnostics=(
            StructuredError(
                "PROVIDER_NOTE",
                "resolver",
                "metadata",
                False,
                "Safe diagnostic",
            ),
        ),
    )


def _fixture(name: str) -> bytes:
    configured = os.environ.get("PREP_ROOT")
    if configured:
        return (Path(configured) / "contracts" / "fixtures" / name).read_bytes()
    return (Path(__file__).resolve().parents[1] / "fixtures" / name).read_bytes()


def test_media_item_round_trip_preserves_complete_identity_losslessly() -> None:
    item = _item()
    encoded = serialize_media_item(item)
    payload = json.loads(encoded)

    assert payload["identity"] == {
        "media_id": "med_0123456789abcdef",
        "identity_kind": "provider",
        "canonical_key": "youtube:video:abc",
    }
    assert "id" not in payload
    assert "stable_source" not in payload
    assert deserialize_media_item(encoded) == item


def test_media_item_prepared_nested_identity_fixture_is_accepted() -> None:
    item = deserialize_media_item(_fixture("media-item-valid-nested-identity.json"))
    assert item.identity.identity_kind == "provider"
    assert item.identity.canonical_key == "youtube:video:fixture-1"


def test_media_item_ambiguous_legacy_flat_fixture_is_rejected() -> None:
    with pytest.raises(MediaItemDecodeError) as raised:
        deserialize_media_item(_fixture("media-item-invalid-flat-identity.json"))
    assert raised.value.code in {"UNKNOWN_PROPERTY", "MISSING_PROPERTY"}


def test_media_item_serialization_is_deterministic_utf8() -> None:
    first = serialize_media_item(_item())
    second = serialize_media_item(deserialize_media_item(first))
    assert first == second
    assert "Grüße 🎵" in first.decode("utf-8")


def test_media_item_is_deeply_immutable() -> None:
    item = _item()
    with pytest.raises(TypeError):
        item.metadata["new"] = True  # type: ignore[index]
    nested = item.metadata["nested"]
    with pytest.raises(TypeError):
        nested["quality"] = "low"  # type: ignore[index]


@pytest.mark.parametrize(
    "changes",
    [
        {"kind": "invalid"},
        {"original_source": ""},
        {"title": "x" * 4097},
        {"availability": "maybe"},
        {"duration_ms": -1},
        {"resume_position_ms": -1},
        {"metadata": {str(index): index for index in range(129)}},
    ],
)
def test_media_item_rejects_invalid_or_over_limit_values(changes: dict) -> None:
    values = {
        "identity": _item().identity,
        "kind": "audio",
        "original_source": "file:///music/example.mp3",
        "title": "Example",
        "availability": "available",
    }
    values.update(changes)
    with pytest.raises(MediaItemValidationError):
        MediaItem(**values)


@pytest.mark.parametrize(
    ("mutator", "code"),
    [
        (lambda value: value.update({"surprise": True}), "UNKNOWN_PROPERTY"),
        (lambda value: value.pop("identity"), "MISSING_PROPERTY"),
        (
            lambda value: value.update(
                {"identity": {**value["identity"], "identity_kind": "wrong"}}
            ),
            "INVALID_VALUE",
        ),
        (lambda value: value.update({"schema_version": 2}), "UNSUPPORTED_SCHEMA_VERSION"),
    ],
)
def test_media_item_decode_rejects_invalid_documents(mutator, code: str) -> None:
    payload = json.loads(serialize_media_item(_item()))
    mutator(payload)
    with pytest.raises(MediaItemDecodeError) as raised:
        deserialize_media_item(json.dumps(payload))
    assert raised.value.code == code


def test_media_item_rejects_non_json_metadata_values() -> None:
    with pytest.raises(MediaItemValidationError):
        MediaItem(
            identity=_item().identity,
            kind="audio",
            original_source="file:///music/example.mp3",
            title="Example",
            availability="available",
            metadata={"bad": object()},
        )
