"""Crash-safe publication and bounded recovery for QueueState snapshots."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile

from .model import QueueState
from .serialization import QueueStateDecodeError, deserialize_queue_state, serialize_queue_state


DEFAULT_MAX_QUEUE_DOCUMENT_BYTES = 64 * 1024 * 1024


class QueuePersistenceError(OSError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class QueueLoadResult:
    state: QueueState
    source: str
    primary_error: QueuePersistenceError | QueueStateDecodeError | None = None
    recovery_error: QueuePersistenceError | QueueStateDecodeError | None = None


class AtomicQueueStateStore:
    """Own one primary file and one bounded recovery copy in the same directory."""

    def __init__(
        self, path: str | os.PathLike[str], *, max_document_bytes: int = DEFAULT_MAX_QUEUE_DOCUMENT_BYTES
    ) -> None:
        self.path = Path(path)
        self.recovery_path = self.path.with_name(f"{self.path.name}.bak")
        if type(max_document_bytes) is not int or max_document_bytes < 1:
            raise ValueError("max_document_bytes must be a positive integer")
        self.max_document_bytes = max_document_bytes

    def save(self, state: QueueState) -> None:
        encoded = serialize_queue_state(state)
        self._check_size(len(encoded))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            if self.path.exists():
                previous = self._read_bounded(self.path)
                deserialize_queue_state(previous)
                self._atomic_write(self.recovery_path, previous)
            temporary = self._write_temp(encoded, self.path.name)
            os.replace(temporary, self.path)
            temporary = None
            self._sync_directory()
        except QueuePersistenceError:
            raise
        except (OSError, QueueStateDecodeError) as error:
            raise QueuePersistenceError("QUEUE_STATE_WRITE_FAILED", str(error)) from error
        finally:
            if temporary is not None:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass

    def load(self, default: QueueState | None = None) -> QueueLoadResult:
        fallback = QueueState.empty() if default is None else default
        if not isinstance(fallback, QueueState):
            raise TypeError("default must be QueueState")
        if not self.path.exists():
            return QueueLoadResult(fallback, "default")
        try:
            return QueueLoadResult(self._decode_path(self.path), "primary")
        except (QueuePersistenceError, QueueStateDecodeError) as primary_error:
            if self.recovery_path.exists():
                try:
                    return QueueLoadResult(
                        self._decode_path(self.recovery_path), "recovery", primary_error
                    )
                except (QueuePersistenceError, QueueStateDecodeError) as recovery_error:
                    return QueueLoadResult(
                        fallback, "default", primary_error, recovery_error
                    )
            return QueueLoadResult(fallback, "default", primary_error)

    def _decode_path(self, path: Path) -> QueueState:
        return deserialize_queue_state(self._read_bounded(path))

    def _read_bounded(self, path: Path) -> bytes:
        try:
            with path.open("rb") as stream:
                data = stream.read(self.max_document_bytes + 1)
        except OSError as error:
            raise QueuePersistenceError("QUEUE_STATE_READ_FAILED", str(error)) from error
        self._check_size(len(data))
        return data

    def _check_size(self, size: int) -> None:
        if size > self.max_document_bytes:
            raise QueuePersistenceError(
                "QUEUE_STATE_OVERSIZE",
                f"document is larger than {self.max_document_bytes} bytes",
            )

    def _atomic_write(self, destination: Path, data: bytes) -> None:
        temporary = self._write_temp(data, destination.name)
        try:
            os.replace(temporary, destination)
            temporary = None
            self._sync_directory()
        finally:
            if temporary is not None:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass

    def _write_temp(self, data: bytes, stem: str) -> Path:
        descriptor, name = tempfile.mkstemp(
            prefix=f".{stem}.", suffix=".tmp", dir=self.path.parent
        )
        path = Path(name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                descriptor = -1
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            return path
        except BaseException:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            raise

    def _sync_directory(self) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(self.path.parent, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
