"""Stable media identity primitives for V7.

Media identity describes a resource. It deliberately contains no queue position,
playback transport URL, or mutable presentation state.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import ClassVar
from uuid import uuid4


class IdentityValidationError(ValueError):
    """Raised when an identity violates the frozen V7 contract."""


@dataclass(frozen=True, slots=True)
class MediaIdentity:
    """Immutable identity of a logical media resource."""

    media_id: str
    identity_kind: str
    canonical_key: str

    ALLOWED_KINDS: ClassVar[frozenset[str]] = frozenset(
        {"local", "network", "provider", "casu", "generated"}
    )
    _ID_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"^med_[A-Za-z0-9_-]{16,120}$"
    )

    def __post_init__(self) -> None:
        if not isinstance(self.media_id, str) or not self._ID_PATTERN.fullmatch(
            self.media_id
        ):
            raise IdentityValidationError("media_id does not match the V7 schema")
        if self.identity_kind not in self.ALLOWED_KINDS:
            raise IdentityValidationError(
                f"unsupported identity_kind: {self.identity_kind!r}"
            )
        if not isinstance(self.canonical_key, str) or not 1 <= len(
            self.canonical_key
        ) <= 4096:
            raise IdentityValidationError(
                "canonical_key must contain between 1 and 4096 characters"
            )

    @classmethod
    def create(cls, identity_kind: str, canonical_key: str) -> MediaIdentity:
        """Create a new schema-compatible identity.

        Canonical-key derivation is owned by later source/provider packets. This
        factory only assigns the opaque stable identifier required by this packet.
        """

        return cls(f"med_{uuid4().hex}", identity_kind, canonical_key)
