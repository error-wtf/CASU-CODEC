"""Bounded playlist model shared by MPCASU queue presentations."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable


MAX_PLAYLIST_ITEMS = 10_000
MAX_PLAYLIST_PATH_BYTES = 4096


class PlaylistError(ValueError):
    pass


class PlaylistModel:
    def __init__(self, items: Iterable[str | Path] = ()):
        self._items: list[Path] = []
        self.add(items)

    @property
    def items(self) -> tuple[Path, ...]:
        return tuple(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def item(self, index: int) -> Path:
        try:
            return self._items[int(index)]
        except (IndexError, ValueError) as exc:
            raise PlaylistError("playlist index is out of range") from exc

    def index_of(self, value: str | Path) -> int | None:
        path = self._path(value)
        try:
            return self._items.index(path)
        except ValueError:
            return None

    @staticmethod
    def _path(value: str | Path) -> Path:
        text = str(value)
        if (not text or "\0" in text
                or len(text.encode("utf-8")) > MAX_PLAYLIST_PATH_BYTES):
            raise PlaylistError("playlist path is invalid")
        return Path(text).expanduser().resolve()

    def add(self, values: Iterable[str | Path], *, existing_only: bool = False) -> int:
        added = 0
        known = {str(item) for item in self._items}
        for value in values:
            path = self._path(value)
            if existing_only and not path.is_file():
                continue
            if str(path) in known:
                continue
            if len(self._items) >= MAX_PLAYLIST_ITEMS:
                raise PlaylistError("playlist item count exceeds limit")
            self._items.append(path)
            known.add(str(path))
            added += 1
        return added

    def remove(self, indices: Iterable[int]) -> None:
        unique = sorted({int(index) for index in indices}, reverse=True)
        if any(index < 0 or index >= len(self._items) for index in unique):
            raise PlaylistError("playlist index is out of range")
        for index in unique:
            del self._items[index]

    def move(self, index: int, delta: int) -> int:
        source, target = int(index), int(index) + int(delta)
        if source < 0 or source >= len(self._items):
            raise PlaylistError("playlist index is out of range")
        if target < 0 or target >= len(self._items):
            return source
        self._items[source], self._items[target] = self._items[target], self._items[source]
        return target

    def clear(self) -> None:
        self._items.clear()

    def to_payload(self) -> dict:
        return {"version": 1, "items": [str(item) for item in self._items]}

    @classmethod
    def from_payload(cls, payload: object, *, existing_only: bool = False):
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise PlaylistError("unsupported playlist document")
        values = payload.get("items")
        if not isinstance(values, list) or len(values) > MAX_PLAYLIST_ITEMS:
            raise PlaylistError("playlist items must be a bounded array")
        if not all(isinstance(value, str) for value in values):
            raise PlaylistError("playlist items must be paths")
        result = cls()
        result.add(values, existing_only=existing_only)
        return result
