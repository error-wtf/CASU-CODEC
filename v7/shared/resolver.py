"""Provider-neutral resolver result envelope and terminal invariants."""

from __future__ import annotations

from dataclasses import dataclass
import json

from .core.errors import StructuredError
from .core.media_item import MediaItem, deserialize_media_item, serialize_media_item
from .limits import QUEUE_OCCURRENCES


class ResolverResultDecodeError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class ResolverResult:
    operation_id: str
    generation: int
    state: str
    items: tuple[MediaItem, ...]
    errors: tuple[StructuredError, ...]
    truncated: bool
    continuation: str | None = None
    elapsed_ms: int = 0
    provider: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.operation_id, str) or not 1 <= len(self.operation_id) <= 128:
            raise ValueError("invalid operation_id")
        if type(self.generation) is not int or self.generation < 0:
            raise ValueError("generation must be non-negative")
        if self.state not in {"ready", "partial", "failed", "cancelled", "timeout"}:
            raise ValueError("invalid resolver state")
        if not isinstance(self.items, tuple) or len(self.items) > QUEUE_OCCURRENCES.maximum or any(not isinstance(x, MediaItem) for x in self.items):
            raise ValueError("invalid resolver items")
        if not isinstance(self.errors, tuple) or len(self.errors) > QUEUE_OCCURRENCES.maximum or any(not isinstance(x, StructuredError) for x in self.errors):
            raise ValueError("invalid resolver errors")
        if type(self.truncated) is not bool:
            raise TypeError("truncated must be boolean")
        if self.continuation is not None and (not isinstance(self.continuation, str) or len(self.continuation) > 8192):
            raise ValueError("invalid continuation")
        if type(self.elapsed_ms) is not int or self.elapsed_ms < 0:
            raise ValueError("elapsed_ms must be non-negative")
        if self.provider is not None and (not isinstance(self.provider, str) or len(self.provider) > 128):
            raise ValueError("invalid provider")
        if self.state == "ready" and (not self.items or self.errors or self.truncated or self.continuation):
            raise ValueError("ready requires items without errors or truncation")
        if self.state == "partial" and (not self.items or (not self.errors and not self.truncated and self.continuation is None)):
            raise ValueError("partial requires items and an explicit partial reason")
        if self.state in {"failed", "cancelled", "timeout"} and self.items:
            raise ValueError("non-success terminal results cannot publish items")
        if self.state in {"failed", "timeout"} and not self.errors:
            raise ValueError("failed and timeout results require errors")
        if self.state == "cancelled" and (self.errors or self.truncated or self.continuation):
            raise ValueError("cancelled result must be clean and terminal")

    @classmethod
    def ready(cls, operation_id: str, generation: int, items: tuple[MediaItem, ...], *, provider: str | None = None, elapsed_ms: int = 0) -> ResolverResult:
        return cls(operation_id, generation, "ready", items, (), False, None, elapsed_ms, provider)

    @classmethod
    def partial(cls, operation_id: str, generation: int, items: tuple[MediaItem, ...], errors: tuple[StructuredError, ...] = (), *, truncated: bool = False, continuation: str | None = None, provider: str | None = None, elapsed_ms: int = 0) -> ResolverResult:
        return cls(operation_id, generation, "partial", items, errors, truncated, continuation, elapsed_ms, provider)

    @classmethod
    def failed(cls, operation_id: str, generation: int, errors: tuple[StructuredError, ...], *, provider: str | None = None, elapsed_ms: int = 0) -> ResolverResult:
        return cls(operation_id, generation, "failed", (), errors, False, None, elapsed_ms, provider)

    @classmethod
    def cancelled(cls, operation_id: str, generation: int, *, provider: str | None = None, elapsed_ms: int = 0) -> ResolverResult:
        return cls(operation_id, generation, "cancelled", (), (), False, None, elapsed_ms, provider)

    @classmethod
    def timeout(cls, operation_id: str, generation: int, error: StructuredError, *, provider: str | None = None, elapsed_ms: int = 0) -> ResolverResult:
        return cls(operation_id, generation, "timeout", (), (error,), False, None, elapsed_ms, provider)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "operation_id": self.operation_id,
            "generation": self.generation,
            "state": self.state,
            "items": [json.loads(serialize_media_item(x)) for x in self.items],
            "errors": [x.to_dict() for x in self.errors],
            "truncated": self.truncated,
            "continuation": self.continuation,
            "elapsed_ms": self.elapsed_ms,
            "provider": self.provider,
        }

    def to_bytes(self) -> bytes:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")

    @classmethod
    def from_bytes(cls, raw: bytes | str) -> ResolverResult:
        try:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            value = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, RecursionError) as error:
            raise ResolverResultDecodeError("MALFORMED_JSON", str(error)) from error
        return cls.from_dict(value)

    @classmethod
    def from_dict(cls, value: object) -> ResolverResult:
        if not isinstance(value, dict):
            raise ResolverResultDecodeError("INVALID_SHAPE", "result must be object")
        required = {"schema_version", "operation_id", "generation", "state", "items", "errors", "truncated"}
        optional = {"continuation", "elapsed_ms", "provider"}
        if set(value) - required - optional:
            raise ResolverResultDecodeError("UNKNOWN_PROPERTY", "unknown result property")
        if required - set(value):
            raise ResolverResultDecodeError("MISSING_PROPERTY", "missing result property")
        if type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ResolverResultDecodeError("UNSUPPORTED_SCHEMA_VERSION", repr(value["schema_version"]))
        if not isinstance(value["items"], list) or not isinstance(value["errors"], list):
            raise ResolverResultDecodeError("INVALID_SHAPE", "items/errors must be arrays")
        try:
            return cls(
                value["operation_id"], value["generation"], value["state"],
                tuple(deserialize_media_item(json.dumps(x)) for x in value["items"]),
                tuple(StructuredError.from_dict(x) for x in value["errors"]),
                value["truncated"], value.get("continuation"), value.get("elapsed_ms", 0), value.get("provider"),
            )
        except (TypeError, ValueError) as error:
            raise ResolverResultDecodeError("INVALID_VALUE", str(error)) from error
