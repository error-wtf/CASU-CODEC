import pytest

from v7.shared.core.errors import ErrorCode, StructuredError
from v7.shared.core.identity import MediaIdentity
from v7.shared.core.media_item import MediaItem
from v7.shared.resolver import ResolverResult, ResolverResultDecodeError


ITEM = MediaItem(
    MediaIdentity("med_0123456789abcdef", "provider", "youtube:video:abc"),
    "youtube", "https://youtube.com/watch?v=abc", "Example", "available",
)
ERROR = StructuredError.for_code(
    ErrorCode.UNAVAILABLE_ENTRY, "resolver", "expand", "Entry unavailable"
)


def test_ready_result_round_trip_preserves_order_and_identity() -> None:
    result = ResolverResult.ready("operation-1", 4, (ITEM,), provider="youtube", elapsed_ms=12)
    encoded = result.to_bytes()
    assert ResolverResult.from_bytes(encoded) == result
    assert ResolverResult.from_bytes(encoded).items[0].identity == ITEM.identity


def test_partial_requires_success_and_explicit_reason() -> None:
    result = ResolverResult.partial("operation-1", 1, (ITEM,), (ERROR,), truncated=True)
    assert result.state == "partial"
    with pytest.raises(ValueError):
        ResolverResult("operation-1", 1, "partial", (), (ERROR,), False)
    with pytest.raises(ValueError):
        ResolverResult("operation-1", 1, "partial", (ITEM,), (), False)


def test_failed_cancelled_and_timeout_are_typed_terminal_results() -> None:
    assert ResolverResult.failed("op", 1, (ERROR,)).state == "failed"
    assert ResolverResult.cancelled("op", 2).state == "cancelled"
    timeout = StructuredError.for_code(ErrorCode.TIMEOUT, "resolver", "expand", "Timed out")
    assert ResolverResult.timeout("op", 3, timeout).state == "timeout"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"operation_id": "", "generation": 0, "state": "cancelled", "items": (), "errors": (), "truncated": False},
        {"operation_id": "op", "generation": -1, "state": "cancelled", "items": (), "errors": (), "truncated": False},
        {"operation_id": "op", "generation": 0, "state": "ready", "items": (), "errors": (), "truncated": False},
        {"operation_id": "op", "generation": 0, "state": "failed", "items": (ITEM,), "errors": (ERROR,), "truncated": False},
        {"operation_id": "op", "generation": 0, "state": "ready", "items": (ITEM,), "errors": (), "truncated": True},
    ],
)
def test_invalid_cross_field_states_are_rejected(kwargs) -> None:
    with pytest.raises(ValueError):
        ResolverResult(**kwargs)


def test_unknown_and_future_documents_are_rejected() -> None:
    payload = ResolverResult.ready("op", 0, (ITEM,)).to_dict()
    payload["extra"] = True
    with pytest.raises(ResolverResultDecodeError) as unknown:
        ResolverResult.from_dict(payload)
    assert unknown.value.code == "UNKNOWN_PROPERTY"
    payload.pop("extra")
    payload["schema_version"] = 2
    with pytest.raises(ResolverResultDecodeError) as future:
        ResolverResult.from_dict(payload)
    assert future.value.code == "UNSUPPORTED_SCHEMA_VERSION"
