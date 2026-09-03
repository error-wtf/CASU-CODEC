import threading

import pytest

from v7.shared.core.errors import ErrorCode, StructuredError
from v7.shared.core.identity import MediaIdentity
from v7.shared.core.media_item import MediaItem
from v7.shared.queue.controller import QueueController, QueueOwnerError
from v7.shared.resolver import ResolverResult


def _item(index: int) -> MediaItem:
    return MediaItem(
        MediaIdentity(f"med_{index:016x}", "generated", f"fixture:{index}"),
        "audio", f"fixture:{index}", f"Item {index}", "available",
    )


def test_resolver_batch_is_applied_atomically_in_order_and_selects_first() -> None:
    controller = QueueController()
    generation = controller.begin_operation("import-1")
    result = ResolverResult.ready("import-1", generation, (_item(1), _item(2)))
    assert controller.apply_resolver_result(result)
    snapshot = controller.snapshot()
    assert [x.media for x in snapshot.state.occurrences] == [_item(1).identity, _item(2).identity]
    assert snapshot.state.current_occurrence_id == snapshot.state.occurrences[0].occurrence_id
    assert snapshot.media_items[_item(1).identity.media_id] == _item(1)


def test_duplicate_media_in_batch_produces_distinct_occurrences() -> None:
    controller = QueueController()
    generation = controller.begin_operation("duplicates")
    item = _item(1)
    controller.apply_resolver_result(ResolverResult.ready("duplicates", generation, (item, item)))
    occurrences = controller.snapshot().state.occurrences
    assert len(occurrences) == 2
    assert occurrences[0].media == occurrences[1].media
    assert occurrences[0].occurrence_id != occurrences[1].occurrence_id


def test_stale_failed_and_cancelled_results_do_not_mutate_queue() -> None:
    controller = QueueController()
    stale = controller.begin_operation("old")
    current = controller.begin_operation("new")
    before = controller.snapshot()
    assert not controller.apply_resolver_result(ResolverResult.ready("old", stale, (_item(1),)))
    error = StructuredError.for_code(ErrorCode.INVALID_INPUT, "resolver", "parse", "Bad input")
    assert not controller.apply_resolver_result(ResolverResult.failed("new", current, (error,)))
    assert controller.snapshot() == before


def test_partial_success_applies_only_evidence_backed_items() -> None:
    controller = QueueController()
    generation = controller.begin_operation("partial")
    warning = StructuredError.for_code(ErrorCode.UNAVAILABLE_ENTRY, "resolver", "expand", "One missing")
    result = ResolverResult.partial("partial", generation, (_item(1),), (warning,))
    assert controller.apply_resolver_result(result)
    assert len(controller.snapshot().state.occurrences) == 1


def test_reusing_operation_id_with_wrong_generation_is_stale() -> None:
    controller = QueueController()
    first = controller.begin_operation("same")
    second = controller.begin_operation("same")
    assert second > first
    assert not controller.apply_resolver_result(ResolverResult.ready("same", first, (_item(1),)))


def test_owner_thread_is_enforced() -> None:
    controller = QueueController()
    failures: list[Exception] = []

    def mutate() -> None:
        try:
            controller.begin_operation("wrong-thread")
        except Exception as error:
            failures.append(error)

    thread = threading.Thread(target=mutate)
    thread.start()
    thread.join()
    assert len(failures) == 1
    assert isinstance(failures[0], QueueOwnerError)


def test_close_invalidates_operations_and_rejects_ingress() -> None:
    controller = QueueController()
    generation = controller.begin_operation("active")
    controller.close()
    assert not controller.apply_resolver_result(ResolverResult.ready("active", generation, (_item(1),)))
    controller.close()
    with pytest.raises(QueueOwnerError):
        controller.begin_operation("later")
