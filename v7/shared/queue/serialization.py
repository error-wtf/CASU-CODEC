"""Strict deterministic serialization for the V7 queue foundation."""

from __future__ import annotations

import json
from typing import Any, NoReturn

from v7.shared.core.identity import IdentityValidationError, MediaIdentity
from v7.shared.queue.model import (
    QueueOccurrence,
    QueueState,
    QueueStateValidationError,
)


class QueueStateDecodeError(ValueError):
    """Typed rejection of an invalid serialized queue snapshot."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


_QUEUE_FIELDS = frozenset(
    {
        "schema_version",
        "revision",
        "occurrences",
        "current_occurrence_id",
        "play_next_ids",
    }
)
_OCCURRENCE_FIELDS = frozenset(
    {"occurrence_id", "media", "insertion_class", "display_title"}
)
_MEDIA_FIELDS = frozenset({"media_id", "identity_kind", "canonical_key"})


def serialize_queue_state(state: QueueState) -> bytes:
    """Return canonical UTF-8 JSON while preserving occurrence/list order."""

    if not isinstance(state, QueueState):
        raise TypeError("state must be a QueueState")
    payload = {
        "schema_version": state.schema_version,
        "revision": state.revision,
        "occurrences": [
            {
                "occurrence_id": occurrence.occurrence_id,
                "media": {
                    "media_id": occurrence.media.media_id,
                    "identity_kind": occurrence.media.identity_kind,
                    "canonical_key": occurrence.media.canonical_key,
                },
                "insertion_class": occurrence.insertion_class,
                "display_title": occurrence.display_title,
            }
            for occurrence in state.occurrences
        ],
        "current_occurrence_id": state.current_occurrence_id,
        "play_next_ids": list(state.play_next_ids),
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")


def deserialize_queue_state(serialized: bytes | str) -> QueueState:
    """Validate a complete snapshot before returning it to the caller.

    The function has no publication side effects, so a failed decode cannot
    mutate or partially replace the caller's previously committed state.
    """

    text: str
    if isinstance(serialized, bytes):
        try:
            text = serialized.decode("utf-8")
        except UnicodeDecodeError as error:
            raise QueueStateDecodeError("INVALID_UTF8", str(error)) from error
    elif isinstance(serialized, str):
        text = serialized
    else:
        raise QueueStateDecodeError(
            "INVALID_INPUT_TYPE", "serialized queue must be bytes or str"
        )

    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, RecursionError) as error:
        raise QueueStateDecodeError("MALFORMED_JSON", str(error)) from error
    if not isinstance(payload, dict):
        raise QueueStateDecodeError("INVALID_SHAPE", "queue root must be an object")

    _require_exact_fields(payload, _QUEUE_FIELDS, "queue")
    schema_version = payload["schema_version"]
    if type(schema_version) is not int:
        raise QueueStateDecodeError(
            "INVALID_SCHEMA_VERSION", "schema_version must be an integer"
        )
    if schema_version != QueueState.CURRENT_SCHEMA_VERSION:
        raise QueueStateDecodeError(
            "UNSUPPORTED_SCHEMA_VERSION",
            f"schema_version {schema_version} is not supported",
        )

    raw_occurrences = payload["occurrences"]
    raw_play_next = payload["play_next_ids"]
    if not isinstance(raw_occurrences, list):
        raise QueueStateDecodeError(
            "INVALID_SHAPE", "occurrences must be an array"
        )
    if not isinstance(raw_play_next, list):
        raise QueueStateDecodeError(
            "INVALID_SHAPE", "play_next_ids must be an array"
        )

    occurrences = tuple(
        _decode_occurrence(item, index) for index, item in enumerate(raw_occurrences)
    )
    try:
        return QueueState(
            schema_version=schema_version,
            revision=payload["revision"],
            occurrences=occurrences,
            current_occurrence_id=payload["current_occurrence_id"],
            play_next_ids=tuple(raw_play_next),
        )
    except QueueStateValidationError as error:
        raise QueueStateDecodeError(
            _validation_code(str(error)), str(error)
        ) from error


def _decode_occurrence(payload: Any, index: int) -> QueueOccurrence:
    if not isinstance(payload, dict):
        raise QueueStateDecodeError(
            "INVALID_SHAPE", f"occurrences[{index}] must be an object"
        )
    _require_exact_fields(payload, _OCCURRENCE_FIELDS, f"occurrences[{index}]")
    media_payload = payload["media"]
    if not isinstance(media_payload, dict):
        raise QueueStateDecodeError(
            "INVALID_SHAPE", f"occurrences[{index}].media must be an object"
        )
    _require_exact_fields(
        media_payload, _MEDIA_FIELDS, f"occurrences[{index}].media"
    )
    try:
        media = MediaIdentity(
            media_id=media_payload["media_id"],
            identity_kind=media_payload["identity_kind"],
            canonical_key=media_payload["canonical_key"],
        )
        return QueueOccurrence(
            occurrence_id=payload["occurrence_id"],
            media=media,
            insertion_class=payload["insertion_class"],
            display_title=payload["display_title"],
        )
    except (IdentityValidationError, QueueStateValidationError) as error:
        raise QueueStateDecodeError("INVALID_VALUE", str(error)) from error


def _require_exact_fields(
    payload: dict[str, Any], expected: frozenset[str], context: str
) -> None:
    actual = set(payload)
    unknown = actual - expected
    if unknown:
        _raise_field_error(
            "UNKNOWN_PROPERTY", f"{context} contains {sorted(unknown)!r}"
        )
    missing = expected - actual
    if missing:
        _raise_field_error(
            "MISSING_PROPERTY", f"{context} lacks {sorted(missing)!r}"
        )


def _raise_field_error(code: str, message: str) -> NoReturn:
    raise QueueStateDecodeError(code, message)


def _validation_code(message: str) -> str:
    if "duplicate occurrence_id" in message:
        return "DUPLICATE_OCCURRENCE_ID"
    if "stale current_occurrence_id" in message:
        return "STALE_CURRENT_OCCURRENCE"
    if "play_next" in message:
        return "INVALID_PLAY_NEXT_MEMBERSHIP"
    if "occurrence limit" in message:
        return "QUEUE_LIMIT_EXCEEDED"
    return "INVALID_QUEUE_STATE"
