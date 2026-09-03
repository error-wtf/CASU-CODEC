"""Strict resolver input splitting and provider classification."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

from .limits import QUEUE_OCCURRENCES
from .source_location import MAX_SOURCE_CHARACTERS


_SEPARATORS = re.compile(r"[,;\r\n]+")
_YOUTUBE_HOSTS = frozenset(
    {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
)
_PLAYLIST_ID = re.compile(r"^[A-Za-z0-9_-]{1,1024}$")


class ResolverInputError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def split_multi_input(text: str, *, limit: int = QUEUE_OCCURRENCES.maximum) -> tuple[str, ...]:
    if not isinstance(text, str) or not text.strip() or "\0" in text or len(text) > MAX_SOURCE_CHARACTERS:
        raise ResolverInputError("INVALID_INPUT", "input is empty, invalid or oversized")
    if type(limit) is not int or not 1 <= limit <= QUEUE_OCCURRENCES.maximum:
        raise ResolverInputError("INVALID_LIMIT", "limit is outside the supported range")
    result: list[str] = []
    for raw in _SEPARATORS.split(text):
        token = raw.strip()
        if not token:
            continue
        if len(token) > MAX_SOURCE_CHARACTERS or "\0" in token:
            raise ResolverInputError("INVALID_INPUT", "token is invalid or oversized")
        if len(result) == limit:
            raise ResolverInputError("INPUT_LIMIT_EXCEEDED", f"input exceeds {limit} tokens")
        result.append(token)
    if not result:
        raise ResolverInputError("INVALID_INPUT", "no non-empty input tokens")
    return tuple(result)


def youtube_playlist_id(url: str) -> str | None:
    if not isinstance(url, str) or not url or len(url) > MAX_SOURCE_CHARACTERS:
        return None
    try:
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in {"http", "https"} or (parsed.hostname or "").lower() not in _YOUTUBE_HOSTS:
            return None
        values = parse_qs(parsed.query, keep_blank_values=True).get("list", ())
        if not values:
            return None
        value = values[0].strip()
        return value if _PLAYLIST_ID.fullmatch(value) else None
    except (TypeError, ValueError, UnicodeError):
        return None
