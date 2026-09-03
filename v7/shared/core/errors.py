"""Immutable structured diagnostics shared by V7 models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import re


class StructuredErrorValidationError(ValueError):
    pass


class StructuredErrorDecodeError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class ErrorCode(str, Enum):
    INVALID_INPUT = "INVALID_INPUT"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    MISSING_DEPENDENCY = "MISSING_DEPENDENCY"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    NETWORK_OFFLINE = "NETWORK_OFFLINE"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    PROVIDER_CHANGED = "PROVIDER_CHANGED"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    GEO_RESTRICTED = "GEO_RESTRICTED"
    UNAVAILABLE_ENTRY = "UNAVAILABLE_ENTRY"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    INTEGRITY_FAILURE = "INTEGRITY_FAILURE"
    DECODER_FAILURE = "DECODER_FAILURE"
    OUTPUT_FINALIZATION_FAILURE = "OUTPUT_FINALIZATION_FAILURE"
    INTERNAL_INVARIANT_VIOLATION = "INTERNAL_INVARIANT_VIOLATION"


_RETRYABLE_CODES = frozenset(
    {ErrorCode.NETWORK_OFFLINE, ErrorCode.TIMEOUT, ErrorCode.PROVIDER_CHANGED}
)


@dataclass(frozen=True, slots=True)
class StructuredError:
    code: str
    subsystem: str
    operation: str
    retryable: bool
    message: str
    safe_detail: str | None = None
    provider: str | None = None
    item_id: str | None = None
    cause_class: str | None = None

    _CODE = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self._CODE.fullmatch(self.code):
            raise StructuredErrorValidationError("invalid error code")
        _bounded(self.subsystem, "subsystem", 1, 128)
        _bounded(self.operation, "operation", 1, 128)
        if type(self.retryable) is not bool:
            raise StructuredErrorValidationError("retryable must be boolean")
        _bounded(self.message, "message", 0, 4096)
        _optional(self.safe_detail, "safe_detail", 16384)
        _optional(self.provider, "provider", 128)
        _optional(self.item_id, "item_id", 128)
        _optional(self.cause_class, "cause_class", 256)
        if self.safe_detail is not None:
            object.__setattr__(self, "safe_detail", redact_sensitive_text(self.safe_detail))

    @classmethod
    def for_code(
        cls,
        code: ErrorCode,
        subsystem: str,
        operation: str,
        message: str,
        **details: str | None,
    ) -> StructuredError:
        if not isinstance(code, ErrorCode):
            raise StructuredErrorValidationError("code must be an ErrorCode")
        return cls(
            code.value,
            subsystem,
            operation,
            code in _RETRYABLE_CODES,
            message,
            **details,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "subsystem": self.subsystem,
            "operation": self.operation,
            "retryable": self.retryable,
            "message": self.message,
            "safe_detail": self.safe_detail,
            "provider": self.provider,
            "item_id": self.item_id,
            "cause_class": self.cause_class,
        }

    @classmethod
    def from_dict(cls, value: object) -> StructuredError:
        if not isinstance(value, dict):
            raise StructuredErrorValidationError("diagnostic must be an object")
        required = {"code", "subsystem", "operation", "retryable", "message"}
        optional = {"safe_detail", "provider", "item_id", "cause_class"}
        if set(value) - required - optional:
            raise StructuredErrorValidationError("unknown diagnostic property")
        if required - set(value):
            raise StructuredErrorValidationError("missing diagnostic property")
        return cls(
            code=value["code"],  # type: ignore[arg-type]
            subsystem=value["subsystem"],  # type: ignore[arg-type]
            operation=value["operation"],  # type: ignore[arg-type]
            retryable=value["retryable"],  # type: ignore[arg-type]
            message=value["message"],  # type: ignore[arg-type]
            safe_detail=value.get("safe_detail"),  # type: ignore[arg-type]
            provider=value.get("provider"),  # type: ignore[arg-type]
            item_id=value.get("item_id"),  # type: ignore[arg-type]
            cause_class=value.get("cause_class"),  # type: ignore[arg-type]
        )


def _bounded(value: object, name: str, minimum: int, maximum: int) -> None:
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise StructuredErrorValidationError(
            f"{name} must contain {minimum}..{maximum} characters"
        )


def _optional(value: object, name: str, maximum: int) -> None:
    if value is not None and (not isinstance(value, str) or len(value) > maximum):
        raise StructuredErrorValidationError(
            f"{name} must be null or at most {maximum} characters"
        )


_BEARER = re.compile(r"(?i)\bbearer\s+[^\s,;]+")
_NAMED_SECRET = re.compile(
    r"(?i)\b(access_token|refresh_token|token|password|passwd|cookie|api[_-]?key)"
    r"(\s*[=:]\s*)"
    r"([^\s&;,]+)"
)
_URL_USERINFO = re.compile(r"(?i)(https?://)([^/@\s]+)@")


def redact_sensitive_text(value: str) -> str:
    """Return bounded diagnostic text with common credential forms removed."""

    if not isinstance(value, str):
        raise StructuredErrorValidationError("diagnostic detail must be text")
    result = _BEARER.sub("Bearer [REDACTED]", value)
    result = _NAMED_SECRET.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", result)
    result = _URL_USERINFO.sub(r"\1[REDACTED]@", result)
    return result


def serialize_structured_error(value: StructuredError) -> bytes:
    if not isinstance(value, StructuredError):
        raise TypeError("value must be StructuredError")
    return json.dumps(
        value.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def deserialize_structured_error(raw: bytes | str) -> StructuredError:
    try:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    except UnicodeDecodeError as error:
        raise StructuredErrorDecodeError("INVALID_UTF8", str(error)) from error
    if not isinstance(text, str):
        raise StructuredErrorDecodeError("INVALID_INPUT_TYPE", "input must be bytes or str")
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, RecursionError) as error:
        raise StructuredErrorDecodeError("MALFORMED_JSON", str(error)) from error
    try:
        return StructuredError.from_dict(value)
    except (StructuredErrorValidationError, TypeError) as error:
        raise StructuredErrorDecodeError("INVALID_VALUE", str(error)) from error
