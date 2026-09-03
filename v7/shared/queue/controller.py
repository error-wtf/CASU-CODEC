"""Owner-thread queue controller with atomic resolver batch publication."""

from __future__ import annotations

from dataclasses import dataclass
import threading
from types import MappingProxyType
from typing import Mapping

from v7.shared.core.media_item import MediaItem
from v7.shared.lifecycle import GenerationGate, OwnerClosedError
from v7.shared.resolver import ResolverResult

from .model import MAX_QUEUE_OCCURRENCES, QueueState, QueueStateValidationError


class QueueOwnerError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class QueueControllerSnapshot:
    state: QueueState
    media_items: Mapping[str, MediaItem]


class QueueController:
    def __init__(self, initial: QueueState | None = None) -> None:
        self._owner_thread = threading.get_ident()
        self._state = QueueState.empty() if initial is None else initial
        self._media_items: dict[str, MediaItem] = {}
        self._gate = GenerationGate()
        self._operation_id: str | None = None
        self._closed = False

    def begin_operation(self, operation_id: str) -> int:
        self._require_owner()
        if self._closed:
            raise QueueOwnerError("queue controller is closed")
        if not isinstance(operation_id, str) or not operation_id:
            raise ValueError("operation_id is required")
        self._operation_id = operation_id
        try:
            return self._gate.begin()
        except OwnerClosedError as error:
            raise QueueOwnerError(str(error)) from error

    def apply_resolver_result(self, result: ResolverResult) -> bool:
        self._require_owner()
        if self._closed or result.operation_id != self._operation_id:
            return False

        def apply() -> bool:
            if result.state not in {"ready", "partial"}:
                return False
            if len(self._state.occurrences) + len(result.items) > MAX_QUEUE_OCCURRENCES:
                raise QueueStateValidationError("atomic batch would exceed queue limit")
            next_state = self._state
            next_items = dict(self._media_items)
            first_new_id: str | None = None
            for item in result.items:
                next_state = next_state.append(item.identity, display_title=item.title)
                next_items[item.identity.media_id] = item
                if first_new_id is None:
                    first_new_id = next_state.occurrences[-1].occurrence_id
            if next_state.current_occurrence_id is None and first_new_id is not None:
                next_state = next_state.with_current(first_new_id)
            self._state = next_state
            self._media_items = next_items
            return True

        published = self._gate.publish(result.generation, apply)
        return bool(published)

    def snapshot(self) -> QueueControllerSnapshot:
        self._require_owner()
        return QueueControllerSnapshot(
            self._state, MappingProxyType(dict(self._media_items))
        )

    def close(self) -> None:
        self._require_owner()
        if not self._closed:
            self._closed = True
            self._operation_id = None
            self._gate.close()

    def _require_owner(self) -> None:
        if threading.get_ident() != self._owner_thread:
            raise QueueOwnerError("queue mutation must run on its owner thread")
