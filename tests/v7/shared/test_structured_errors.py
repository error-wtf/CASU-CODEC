"""Structured error, retry and redaction contract tests."""

import json

import pytest

from v7.shared.core.errors import (
    ErrorCode,
    StructuredError,
    StructuredErrorDecodeError,
    StructuredErrorValidationError,
    deserialize_structured_error,
    redact_sensitive_text,
    serialize_structured_error,
)


def test_error_round_trip_is_deterministic_and_schema_shaped() -> None:
    error = StructuredError.for_code(
        ErrorCode.NETWORK_OFFLINE,
        subsystem="resolver",
        operation="fetch",
        message="Network unavailable",
        safe_detail="GET https://example.invalid/media",
        item_id="med_0123456789abcdef",
    )
    encoded = serialize_structured_error(error)
    assert encoded == serialize_structured_error(deserialize_structured_error(encoded))
    assert json.loads(encoded)["retryable"] is True


@pytest.mark.parametrize(
    ("code", "retryable"),
    [
        (ErrorCode.NETWORK_OFFLINE, True),
        (ErrorCode.TIMEOUT, True),
        (ErrorCode.INVALID_INPUT, False),
        (ErrorCode.PERMISSION_DENIED, False),
        (ErrorCode.CANCELLED, False),
        (ErrorCode.INTERNAL_INVARIANT_VIOLATION, False),
    ],
)
def test_error_code_factory_applies_canonical_retryability(code, retryable) -> None:
    value = StructuredError.for_code(code, "core", "operation", "Safe message")
    assert value.retryable is retryable


def test_sensitive_details_are_redacted_at_construction_boundary() -> None:
    value = StructuredError(
        "AUTHENTICATION_REQUIRED",
        "provider",
        "login",
        False,
        "Authentication required",
        "Bearer abc.secret token=raw password=hunter2 https://user:pass@example.com/a",
    )
    detail = value.safe_detail or ""
    assert "abc.secret" not in detail
    assert "raw" not in detail
    assert "hunter2" not in detail
    assert "user:pass" not in detail
    assert detail.count("[REDACTED]") >= 4


def test_redaction_is_idempotent() -> None:
    once = redact_sensitive_text("cookie=session-secret&access_token=abc")
    assert redact_sensitive_text(once) == once


@pytest.mark.parametrize(
    "value",
    [
        {"code": "bad", "subsystem": "core", "operation": "x", "retryable": False, "message": "x"},
        {"code": "INVALID_INPUT", "subsystem": "", "operation": "x", "retryable": False, "message": "x"},
        {"code": "INVALID_INPUT", "subsystem": "core", "operation": "x", "retryable": 1, "message": "x"},
    ],
)
def test_invalid_error_values_are_rejected(value) -> None:
    with pytest.raises(StructuredErrorValidationError):
        StructuredError.from_dict(value)


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (b"not json", "MALFORMED_JSON"),
        (json.dumps({"code": "INVALID_INPUT"}).encode(), "INVALID_VALUE"),
        (
            json.dumps(
                {
                    "code": "INVALID_INPUT",
                    "subsystem": "core",
                    "operation": "parse",
                    "retryable": False,
                    "message": "bad",
                    "unexpected": True,
                }
            ).encode(),
            "INVALID_VALUE",
        ),
    ],
)
def test_error_decoder_rejects_malformed_and_invalid(payload: bytes, code: str) -> None:
    with pytest.raises(StructuredErrorDecodeError) as raised:
        deserialize_structured_error(payload)
    assert raised.value.code == code
