"""Immutable structured diagnostics shared by V7 models."""

from __future__ import annotations

from dataclasses import dataclass
import re


class StructuredErrorValidationError(ValueError):
    pass


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
