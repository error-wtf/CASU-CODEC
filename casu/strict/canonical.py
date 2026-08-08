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
    source_width: int | None = None
    source_height: int | None = None

    @property
    def shape(self) -> tuple[int, ...]:
        if self.source_width is not None and self.source_height is not None:
            return (self.source_height, self.source_width)
        return tuple(int(value) for value in self.planes[0].shape)

    def digest(self) -> str:
        digest = hashlib.sha256()
        digest.update(self.pixel_format.encode("utf-8"))
        digest.update(f"{self.shape[1]}x{self.shape[0]}".encode("ascii"))
        digest.update(repr(self.color_metadata).encode("utf-8"))
        for plane in self.planes:
            digest.update(str(plane.shape).encode("ascii"))
            digest.update(str(plane.dtype).encode("ascii"))
            digest.update(plane.tobytes(order="C"))
        return digest.hexdigest()


def canonical_frame(planes: np.ndarray | Sequence[np.ndarray], *, pixel_format: str = "gray8",
                    color_metadata: Mapping[str, Any] | None = None,
                    source_shape: tuple[int, int] | None = None) -> CanonicalFrame:
    values = (planes,) if isinstance(planes, np.ndarray) else tuple(planes)
    if not values:
        raise StrictCanonicalError("at least one decoded plane is required")
    canonical: list[np.ndarray] = []
    for value in values:
        array = np.asarray(value)
        if array.ndim != 2 or array.size == 0:
            raise StrictCanonicalError("each canonical plane must be a non-empty 2D array")
        if array.dtype.kind not in "ui" or array.dtype.itemsize not in (1, 2):
            raise StrictCanonicalError("canonical planes must use 8- or 16-bit integer samples")
        array = np.ascontiguousarray(array)
        canonical.append(array)
    if source_shape is not None:
        if len(source_shape) != 2 or any(int(v) <= 0 for v in source_shape):
            raise StrictCanonicalError("source_shape must be (height, width)")
        source_height, source_width = (int(source_shape[0]), int(source_shape[1]))
        packed = str(pixel_format) in {"rgb24", "rgba", "rgba64le"}
        if canonical[0].shape[0] > source_height or (not packed and canonical[0].shape[1] > source_width):
            raise StrictCanonicalError("plane exceeds source resolution")
    else:
        source_height, source_width = (int(canonical[0].shape[0]), int(canonical[0].shape[1]))
    metadata = tuple(sorted((str(key), str(value)) for key, value in (color_metadata or {}).items()))
    return CanonicalFrame(tuple(canonical), str(pixel_format), metadata, source_width, source_height)
