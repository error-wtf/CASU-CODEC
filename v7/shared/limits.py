"""Named V7 resource budgets shared by model and service boundaries."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResourceLimit:
    name: str
    maximum: int
    unit: str
    failure_code: str

    def __post_init__(self) -> None:
        if not self.name or type(self.maximum) is not int or self.maximum < 1:
            raise ValueError("resource limit requires a name and positive maximum")
        if not self.unit or not self.failure_code:
            raise ValueError("resource limit requires unit and failure code")

    def require(self, observed: int) -> None:
        if type(observed) is not int or observed < 0:
            raise ValueError("observed value must be a non-negative integer")
        if observed > self.maximum:
            raise LimitExceededError(self, observed)


class LimitExceededError(ValueError):
    def __init__(self, limit: ResourceLimit, observed: int) -> None:
        self.limit = limit
        self.observed = observed
        super().__init__(
            f"{limit.failure_code}: {limit.name} {observed} exceeds "
            f"{limit.maximum} {limit.unit}"
        )


QUEUE_OCCURRENCES = ResourceLimit("queue_occurrences", 10_000, "items", "QUEUE_LIMIT_EXCEEDED")
QUEUE_DOCUMENT_BYTES = ResourceLimit("queue_document", 64 * 1024 * 1024, "bytes", "QUEUE_STATE_OVERSIZE")
SETTINGS_DOCUMENT_BYTES = ResourceLimit("settings_document", 1024 * 1024, "bytes", "SETTINGS_OVERSIZE")
WATCHED_FOLDERS = ResourceLimit("watched_folders", 100, "items", "SETTINGS_LIMIT_EXCEEDED")
SETTING_TEXT_BYTES = ResourceLimit("setting_text", 4096, "bytes", "SETTINGS_LIMIT_EXCEEDED")
MEDIA_METADATA_PROPERTIES = ResourceLimit("media_metadata", 128, "properties", "MEDIA_ITEM_LIMIT_EXCEEDED")
MEDIA_DIAGNOSTICS = ResourceLimit("media_diagnostics", 64, "items", "MEDIA_ITEM_LIMIT_EXCEEDED")
NETWORK_CHUNK_BYTES = ResourceLimit("network_chunk", 256 * 1024, "bytes", "NETWORK_LIMIT_EXCEEDED")

NETWORK_UPSTREAM_TIMEOUT_SECONDS = 20.0
NETWORK_HANDLER_IDLE_TIMEOUT_SECONDS = 10.0
