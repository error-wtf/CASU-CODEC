from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np


class StrictCanonicalError(ValueError):
    pass


@dataclass(frozen=True)
class CanonicalFrame:
    """Immutable decoded planes plus the metadata needed for strict identity."""
    planes: tuple[np.ndarray, ...]
    pixel_format: str
    color_metadata: tuple[tuple[str, str], ...] = ()

    @property
    def shape(self) -> tuple[int, ...]:
        return tuple(int(value) for value in self.planes[0].shape)

    def digest(self) -> str:
        digest = hashlib.sha256()
        digest.update(self.pixel_format.encode("utf-8"))
        digest.update(repr(self.color_metadata).encode("utf-8"))
        for plane in self.planes:
            digest.update(str(plane.shape).encode("ascii"))
            digest.update(str(plane.dtype).encode("ascii"))
            digest.update(plane.tobytes(order="C"))
        return digest.hexdigest()


def canonical_frame(planes: np.ndarray | Sequence[np.ndarray], *, pixel_format: str = "gray8",
                    color_metadata: Mapping[str, Any] | None = None) -> CanonicalFrame:
    values = (planes,) if isinstance(planes, np.ndarray) else tuple(planes)
    if not values:
        raise StrictCanonicalError("at least one decoded plane is required")
    canonical: list[np.ndarray] = []
    first_shape: tuple[int, ...] | None = None
    for value in values:
        array = np.asarray(value)
        if array.ndim != 2 or array.size == 0:
            raise StrictCanonicalError("each canonical plane must be a non-empty 2D array")
        if array.dtype.kind not in "ui" or array.dtype.itemsize not in (1, 2):
            raise StrictCanonicalError("canonical planes must use 8- or 16-bit integer samples")
        array = np.ascontiguousarray(array)
        if first_shape is None:
            first_shape = tuple(int(v) for v in array.shape)
        if tuple(int(v) for v in array.shape) != first_shape:
            raise StrictCanonicalError("all planes must use the same source resolution")
        canonical.append(array)
    metadata = tuple(sorted((str(key), str(value)) for key, value in (color_metadata or {}).items()))
    return CanonicalFrame(tuple(canonical), str(pixel_format), metadata)
