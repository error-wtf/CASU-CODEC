"""Transactional publication boundary for cancellable V7 jobs."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from typing import BinaryIO, Callable

from .lifecycle import CancellationToken


class OutputCollisionError(FileExistsError):
    pass


@dataclass(frozen=True, slots=True)
class PublishedOutput:
    path: Path
    size: int


def atomic_output(
    destination: str | Path,
    writer: Callable[[BinaryIO, CancellationToken], None],
    *,
    cancellation: CancellationToken,
    overwrite: bool = False,
) -> PublishedOutput:
    """Write, fsync and atomically publish output; never expose partial data."""
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not overwrite:
        raise OutputCollisionError(str(target))
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".partial", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            cancellation.raise_if_cancelled()
            writer(stream, cancellation)
            cancellation.raise_if_cancelled()
            stream.flush()
            os.fsync(stream.fileno())
        if target.exists() and not overwrite:
            raise OutputCollisionError(str(target))
        os.replace(temporary, target)
        return PublishedOutput(target, target.stat().st_size)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise

