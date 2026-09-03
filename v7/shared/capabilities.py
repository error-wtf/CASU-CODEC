"""Honest, immutable capability negotiation for V7 front ends."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class CapabilityState(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    PERMISSION_REQUIRED = "permission_required"
    DEVICE_REQUIRED = "device_required"


@dataclass(frozen=True, slots=True)
class Capability:
    capability_id: str
    state: CapabilityState
    reason: str | None = None
    remediation: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.capability_id, str) or not self.capability_id or len(self.capability_id) > 128:
            raise ValueError("invalid capability_id")
        if not isinstance(self.state, CapabilityState):
            raise TypeError("state must be CapabilityState")
        for name in ("reason", "remediation"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value or len(value) > 1024):
                raise ValueError(f"invalid {name}")
        if self.state is CapabilityState.AVAILABLE and (self.reason or self.remediation):
            raise ValueError("available capability cannot carry failure guidance")
        if self.state is not CapabilityState.AVAILABLE and not self.reason:
            raise ValueError("unavailable capability requires a reason")

    @property
    def enabled(self) -> bool:
        return self.state is CapabilityState.AVAILABLE


class CapabilityManifest:
    """Atomic snapshot consumed by UIs instead of scattered platform checks."""

    __slots__ = ("_entries", "generation")

    def __init__(self, entries: Mapping[str, Capability], *, generation: int = 0) -> None:
        if type(generation) is not int or generation < 0:
            raise ValueError("generation must be non-negative")
        copied = dict(entries)
        if len(copied) > 512:
            raise ValueError("too many capabilities")
        for key, value in copied.items():
            if not isinstance(value, Capability) or key != value.capability_id:
                raise ValueError("capability key and value must agree")
        self._entries = MappingProxyType(copied)
        self.generation = generation

    @property
    def entries(self) -> Mapping[str, Capability]:
        return self._entries

    def get(self, capability_id: str) -> Capability:
        try:
            return self._entries[capability_id]
        except KeyError as error:
            raise KeyError(f"undeclared capability: {capability_id}") from error

    def enabled(self, capability_id: str) -> bool:
        return self.get(capability_id).enabled

    def replace(self, capability: Capability) -> "CapabilityManifest":
        entries = dict(self._entries)
        entries[capability.capability_id] = capability
        return CapabilityManifest(entries, generation=self.generation + 1)

