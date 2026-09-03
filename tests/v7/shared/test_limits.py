import pytest

from v7.shared.limits import (
    LimitExceededError,
    QUEUE_DOCUMENT_BYTES,
    QUEUE_OCCURRENCES,
    SETTINGS_DOCUMENT_BYTES,
)


@pytest.mark.parametrize(
    "limit",
    [QUEUE_OCCURRENCES, QUEUE_DOCUMENT_BYTES, SETTINGS_DOCUMENT_BYTES],
)
def test_limits_accept_equal_and_reject_over_boundary(limit) -> None:
    limit.require(limit.maximum)
    with pytest.raises(LimitExceededError) as raised:
        limit.require(limit.maximum + 1)
    assert raised.value.limit is limit
    assert raised.value.observed == limit.maximum + 1


def test_limits_name_units_and_failure_code() -> None:
    assert QUEUE_OCCURRENCES.unit == "items"
    assert QUEUE_OCCURRENCES.failure_code == "QUEUE_LIMIT_EXCEEDED"
    assert SETTINGS_DOCUMENT_BYTES.maximum == 1024 * 1024
