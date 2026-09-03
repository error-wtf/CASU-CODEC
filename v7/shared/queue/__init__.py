"""V7 queue foundation."""

from .model import (
    MAX_QUEUE_OCCURRENCES,
    OccurrenceNotFoundError,
    QueueOccurrence,
    QueueState,
    QueueStateValidationError,
)
from .serialization import (
    QueueStateDecodeError,
    deserialize_queue_state,
    serialize_queue_state,
)
from .persistence import AtomicQueueStateStore, QueueLoadResult, QueuePersistenceError
from .controller import QueueController, QueueControllerSnapshot, QueueOwnerError

__all__ = [
    "MAX_QUEUE_OCCURRENCES",
    "AtomicQueueStateStore",
    "OccurrenceNotFoundError",
    "QueueOccurrence",
    "QueueState",
    "QueueStateDecodeError",
    "QueueLoadResult",
    "QueueController",
    "QueueControllerSnapshot",
    "QueueOwnerError",
    "QueuePersistenceError",
    "QueueStateValidationError",
    "deserialize_queue_state",
    "serialize_queue_state",
]
