"""Immutable queue occurrence and queue state models for V7."""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import ClassVar, Literal
from uuid import uuid4

from v7.shared.core.identity import MediaIdentity
from v7.shared.limits import QUEUE_OCCURRENCES


MAX_QUEUE_OCCURRENCES = QUEUE_OCCURRENCES.maximum
InsertionClass = Literal["permanent", "play_next"]


class QueueStateValidationError(ValueError):
    """Raised when a queue snapshot violates the V7 invariant set."""


class OccurrenceNotFoundError(LookupError):
    """Raised when an occurrence-addressed operation has no matching target."""


@dataclass(frozen=True, slots=True)
class QueueOccurrence:
    """One independently addressable insertion of a media resource."""

    occurrence_id: str
    media: MediaIdentity
    insertion_class: InsertionClass = "permanent"
    display_title: str | None = None

    _ID_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"^occ_[A-Za-z0-9_-]{16,120}$"
    )

    def __post_init__(self) -> None:
        if not isinstance(self.occurrence_id, str) or not self._ID_PATTERN.fullmatch(
            self.occurrence_id
        ):
            raise QueueStateValidationError(
                "occurrence_id does not match the V7 schema"
            )
        if not isinstance(self.media, MediaIdentity):
            raise QueueStateValidationError("media must be a MediaIdentity")
        if self.insertion_class not in ("permanent", "play_next"):
            raise QueueStateValidationError(
                f"unsupported insertion_class: {self.insertion_class!r}"
            )
        if self.display_title is not None and (
            not isinstance(self.display_title, str) or len(self.display_title) > 1024
        ):
            raise QueueStateValidationError(
                "display_title must be null or at most 1024 characters"
            )

    @classmethod
    def create(
        cls,
        media: MediaIdentity,
        insertion_class: InsertionClass = "permanent",
        display_title: str | None = None,
    ) -> QueueOccurrence:
        """Create a fresh occurrence for every insertion, including duplicates."""

        return cls(f"occ_{uuid4().hex}", media, insertion_class, display_title)


@dataclass(frozen=True, slots=True)
class QueueState:
    """A validated, immutable queue snapshot.

    Mutating operations return a new snapshot and address queue entries only by
    QueueOccurrenceIdentity. MediaIdentity is intentionally not accepted.
    """

    schema_version: int
    revision: int
    occurrences: tuple[QueueOccurrence, ...]
    current_occurrence_id: str | None
    play_next_ids: tuple[str, ...]

    CURRENT_SCHEMA_VERSION: ClassVar[int] = 1

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int:
            raise QueueStateValidationError("schema_version must be an integer")
        if self.schema_version != self.CURRENT_SCHEMA_VERSION:
            raise QueueStateValidationError(
                f"unsupported schema_version: {self.schema_version}"
            )
        if type(self.revision) is not int or self.revision < 0:
            raise QueueStateValidationError(
                "revision must be a non-negative integer"
            )
        if not isinstance(self.occurrences, tuple):
            raise QueueStateValidationError("occurrences must be an immutable tuple")
        if len(self.occurrences) > MAX_QUEUE_OCCURRENCES:
            raise QueueStateValidationError(
                f"queue exceeds the {MAX_QUEUE_OCCURRENCES} occurrence limit"
            )
        if any(not isinstance(item, QueueOccurrence) for item in self.occurrences):
            raise QueueStateValidationError(
                "occurrences must contain QueueOccurrence values"
            )

        occurrence_ids = tuple(item.occurrence_id for item in self.occurrences)
        occurrence_id_set = set(occurrence_ids)
        if len(occurrence_id_set) != len(occurrence_ids):
            raise QueueStateValidationError("duplicate occurrence_id")
        if self.current_occurrence_id is not None:
            if (
                not isinstance(self.current_occurrence_id, str)
                or self.current_occurrence_id not in occurrence_id_set
            ):
                raise QueueStateValidationError("stale current_occurrence_id")

        if not isinstance(self.play_next_ids, tuple):
            raise QueueStateValidationError("play_next_ids must be an immutable tuple")
        if any(not isinstance(item, str) for item in self.play_next_ids):
            raise QueueStateValidationError("play_next_ids must contain identifiers")
        if len(set(self.play_next_ids)) != len(self.play_next_ids):
            raise QueueStateValidationError("duplicate play_next occurrence_id")
        expected_play_next = {
            item.occurrence_id
            for item in self.occurrences
            if item.insertion_class == "play_next"
        }
        if set(self.play_next_ids) != expected_play_next:
            raise QueueStateValidationError(
                "play_next_ids must exactly reference play_next occurrences"
            )

    @classmethod
    def empty(cls) -> QueueState:
        return cls(cls.CURRENT_SCHEMA_VERSION, 0, (), None, ())

    def append(
        self,
        media: MediaIdentity,
        insertion_class: InsertionClass = "permanent",
        display_title: str | None = None,
        *,
        occurrence_id: str | None = None,
    ) -> QueueState:
        if len(self.occurrences) >= MAX_QUEUE_OCCURRENCES:
            raise QueueStateValidationError(
                f"queue exceeds the {MAX_QUEUE_OCCURRENCES} occurrence limit"
            )
        occurrence = (
            QueueOccurrence.create(media, insertion_class, display_title)
            if occurrence_id is None
            else QueueOccurrence(
                occurrence_id, media, insertion_class, display_title
            )
        )
        play_next_ids = self.play_next_ids
        if insertion_class == "play_next":
            play_next_ids += (occurrence.occurrence_id,)
        return replace(
            self,
            revision=self.revision + 1,
            occurrences=self.occurrences + (occurrence,),
            play_next_ids=play_next_ids,
        )

    def remove(self, occurrence_id: str) -> QueueState:
        index = self._index_of(occurrence_id)
        occurrence = self.occurrences[index]
        return replace(
            self,
            revision=self.revision + 1,
            occurrences=self.occurrences[:index] + self.occurrences[index + 1 :],
            current_occurrence_id=(
                None
                if self.current_occurrence_id == occurrence_id
                else self.current_occurrence_id
            ),
            play_next_ids=(
                tuple(item for item in self.play_next_ids if item != occurrence_id)
                if occurrence.insertion_class == "play_next"
                else self.play_next_ids
            ),
        )

    def move(self, occurrence_id: str, target_index: int) -> QueueState:
        source_index = self._index_of(occurrence_id)
        if type(target_index) is not int or not 0 <= target_index < len(
            self.occurrences
        ):
            raise IndexError("target_index is outside the queue")
        if source_index == target_index:
            return self
        reordered = list(self.occurrences)
        occurrence = reordered.pop(source_index)
        reordered.insert(target_index, occurrence)
        return replace(
            self, revision=self.revision + 1, occurrences=tuple(reordered)
        )

    def with_current(self, occurrence_id: str | None) -> QueueState:
        if occurrence_id is not None:
            self._index_of(occurrence_id)
        if occurrence_id == self.current_occurrence_id:
            return self
        return replace(
            self,
            revision=self.revision + 1,
            current_occurrence_id=occurrence_id,
        )

    def _index_of(self, occurrence_id: str) -> int:
        if not isinstance(occurrence_id, str):
            raise OccurrenceNotFoundError(occurrence_id)
        for index, occurrence in enumerate(self.occurrences):
            if occurrence.occurrence_id == occurrence_id:
                return index
        raise OccurrenceNotFoundError(occurrence_id)
