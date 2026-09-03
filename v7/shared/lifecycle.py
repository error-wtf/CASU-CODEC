"""Thread-safe generation and cooperative cancellation primitives for V7."""

from __future__ import annotations

from collections.abc import Callable
import threading
from typing import TypeVar


T = TypeVar("T")


class OwnerClosedError(RuntimeError):
    pass


class CancelledOperation(RuntimeError):
    pass


class GenerationGate:
    """Owner-side guard preventing obsolete asynchronous publication."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._generation = 0
        self._closed = False

    @property
    def current_generation(self) -> int:
        with self._lock:
            return self._generation

    def begin(self) -> int:
        with self._lock:
            if self._closed:
                raise OwnerClosedError("owner is closed")
            self._generation += 1
            return self._generation

    def invalidate(self) -> int:
        with self._lock:
            self._generation += 1
            return self._generation

    def is_current(self, generation: int) -> bool:
        with self._lock:
            return not self._closed and generation == self._generation

    def publish(self, generation: int, callback: Callable[[], T]) -> T | None:
        """Invoke callback only while the generation remains current.

        The owner must arrange UI-thread marshalling before calling this method.
        The lock remains held through the small publication callback so a
        replacement cannot interleave between validation and mutation.
        """
        with self._lock:
            if self._closed or generation != self._generation:
                return None
            return callback()

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._closed = True
                self._generation += 1


class CancellationToken:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cancelled = False
        self._callbacks: list[Callable[[], None]] = []

    @property
    def cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise CancelledOperation("operation was cancelled")

    def add_callback(self, callback: Callable[[], None]) -> None:
        if not callable(callback):
            raise TypeError("callback must be callable")
        run_now = False
        with self._lock:
            if self._cancelled:
                run_now = True
            else:
                self._callbacks.append(callback)
        if run_now:
            callback()

    def _cancel(self) -> tuple[str, ...] | bool:
        with self._lock:
            if self._cancelled:
                return False
            self._cancelled = True
            callbacks = tuple(self._callbacks)
            self._callbacks.clear()
        failures: list[str] = []
        for callback in callbacks:
            try:
                callback()
            except Exception as error:
                failures.append(str(error))
        return tuple(failures) if failures else True


class CancellationSource:
    def __init__(self) -> None:
        self.token = CancellationToken()

    def cancel(self) -> tuple[str, ...] | bool:
        return self.token._cancel()
