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

__all__ = [
    "MAX_QUEUE_OCCURRENCES",
    "OccurrenceNotFoundError",
    "QueueOccurrence",
    "QueueState",
    "QueueStateDecodeError",
    "QueueStateValidationError",
    "deserialize_queue_state",
    "serialize_queue_state",
]
