"""Persistent, platform-neutral V7 MediaItem envelope."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
import math
from types import MappingProxyType
from typing import Any

from .errors import StructuredError, StructuredErrorValidationError
from .identity import IdentityValidationError, MediaIdentity
from v7.shared.limits import MEDIA_DIAGNOSTICS, MEDIA_METADATA_PROPERTIES


MEDIA_KINDS = frozenset(
    {
        "audio", "video", "stream", "youtube", "spotify", "provider",
        "playlist", "casunat1", "casunat2", "mp5", "legacy-sidecar", "unknown",
    }
)
AVAILABILITY = frozenset(
    {"available", "unavailable", "private", "deleted", "unknown", "error"}
)


class MediaItemValidationError(ValueError):
    pass


class MediaItemDecodeError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class MediaItem:
    identity: MediaIdentity
    kind: str
    original_source: str
    title: str
    availability: str
    artist: str | None = None
    album: str | None = None
    channel: str | None = None
    duration_ms: int | None = None
    thumbnail: str | None = None
    provider: str | None = None
    provider_id: str | None = None
    group_id: str | None = None
    ordinal: int | None = None
    resume_position_ms: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)
    diagnostics: tuple[StructuredError, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.identity, MediaIdentity):
            raise MediaItemValidationError("identity must be MediaIdentity")
        if self.kind not in MEDIA_KINDS:
            raise MediaItemValidationError("invalid media kind")
        _string(self.original_source, "original_source", 1, 16384)
        _string(self.title, "title", 0, 4096)
        if self.availability not in AVAILABILITY:
            raise MediaItemValidationError("invalid availability")
        for name in ("artist", "album", "channel"):
            _optional_string(getattr(self, name), name, 4096)
        _optional_string(self.thumbnail, "thumbnail", 16384)
        _optional_string(self.provider, "provider", 128)
        _optional_string(self.provider_id, "provider_id", 1024)
        _optional_string(self.group_id, "group_id", 128)
        _optional_nonnegative_int(self.duration_ms, "duration_ms")
        _optional_nonnegative_int(self.ordinal, "ordinal")
        if type(self.resume_position_ms) is not int or self.resume_position_ms < 0:
            raise MediaItemValidationError("resume_position_ms must be non-negative")
        if not isinstance(self.metadata, Mapping) or len(self.metadata) > MEDIA_METADATA_PROPERTIES.maximum:
            raise MediaItemValidationError("metadata must be an object with at most 128 properties")
        try:
            frozen = _freeze_json(dict(self.metadata))
        except (TypeError, ValueError) as error:
            raise MediaItemValidationError(str(error)) from error
        object.__setattr__(self, "metadata", frozen)
        if not isinstance(self.diagnostics, tuple) or len(self.diagnostics) > MEDIA_DIAGNOSTICS.maximum:
            raise MediaItemValidationError("diagnostics must contain at most 64 entries")
        if any(not isinstance(value, StructuredError) for value in self.diagnostics):
            raise MediaItemValidationError("diagnostics must contain StructuredError values")


_REQUIRED = {"schema_version", "identity", "kind", "original_source", "title", "availability"}
_OPTIONAL = {
    "artist", "album", "channel", "duration_ms", "thumbnail", "provider",
    "provider_id", "group_id", "ordinal", "resume_position_ms", "metadata", "diagnostics",
}


def serialize_media_item(item: MediaItem) -> bytes:
    if not isinstance(item, MediaItem):
        raise TypeError("item must be MediaItem")
    payload = {
        "schema_version": 1,
        "identity": {
            "media_id": item.identity.media_id,
            "identity_kind": item.identity.identity_kind,
            "canonical_key": item.identity.canonical_key,
        },
        "kind": item.kind,
        "original_source": item.original_source,
        "title": item.title,
        "availability": item.availability,
        "artist": item.artist,
        "album": item.album,
        "channel": item.channel,
        "duration_ms": item.duration_ms,
        "thumbnail": item.thumbnail,
        "provider": item.provider,
        "provider_id": item.provider_id,
        "group_id": item.group_id,
        "ordinal": item.ordinal,
        "resume_position_ms": item.resume_position_ms,
        "metadata": _thaw_json(item.metadata),
        "diagnostics": [value.to_dict() for value in item.diagnostics],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def deserialize_media_item(raw: bytes | str) -> MediaItem:
    try:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    except UnicodeDecodeError as error:
        raise MediaItemDecodeError("INVALID_UTF8", str(error)) from error
    if not isinstance(text, str):
        raise MediaItemDecodeError("INVALID_INPUT_TYPE", "input must be bytes or str")
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, RecursionError) as error:
        raise MediaItemDecodeError("MALFORMED_JSON", str(error)) from error
    if not isinstance(value, dict):
        raise MediaItemDecodeError("INVALID_SHAPE", "MediaItem must be an object")
    unknown = set(value) - _REQUIRED - _OPTIONAL
    missing = _REQUIRED - set(value)
    if unknown:
        raise MediaItemDecodeError("UNKNOWN_PROPERTY", repr(sorted(unknown)))
    if missing:
        raise MediaItemDecodeError("MISSING_PROPERTY", repr(sorted(missing)))
    if value["schema_version"] != 1 or type(value["schema_version"]) is not int:
        raise MediaItemDecodeError("UNSUPPORTED_SCHEMA_VERSION", repr(value["schema_version"]))
    identity = value["identity"]
    if not isinstance(identity, dict) or set(identity) != {"media_id", "identity_kind", "canonical_key"}:
        raise MediaItemDecodeError("INVALID_VALUE", "invalid identity object")
    try:
        return MediaItem(
            identity=MediaIdentity(**identity),
            kind=value["kind"], original_source=value["original_source"],
            title=value["title"], availability=value["availability"],
            artist=value.get("artist"), album=value.get("album"), channel=value.get("channel"),
            duration_ms=value.get("duration_ms"), thumbnail=value.get("thumbnail"),
            provider=value.get("provider"), provider_id=value.get("provider_id"),
            group_id=value.get("group_id"), ordinal=value.get("ordinal"),
            resume_position_ms=value.get("resume_position_ms", 0),
            metadata=value.get("metadata", {}),
            diagnostics=tuple(StructuredError.from_dict(item) for item in value.get("diagnostics", [])),
        )
    except (IdentityValidationError, MediaItemValidationError, StructuredErrorValidationError, TypeError) as error:
        raise MediaItemDecodeError("INVALID_VALUE", str(error)) from error


def _string(value: object, name: str, minimum: int, maximum: int) -> None:
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise MediaItemValidationError(f"invalid {name}")


def _optional_string(value: object, name: str, maximum: int) -> None:
    if value is not None and (not isinstance(value, str) or len(value) > maximum):
        raise MediaItemValidationError(f"invalid {name}")


def _optional_nonnegative_int(value: object, name: str) -> None:
    if value is not None and (type(value) is not int or value < 0):
        raise MediaItemValidationError(f"invalid {name}")


def _freeze_json(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("metadata numbers must be finite")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("metadata object keys must be strings")
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    raise TypeError("metadata contains a non-JSON value")


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value
