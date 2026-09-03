"""Bounded source classification without path/URI identity loss."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit


MAX_SOURCE_CHARACTERS = 16_384
_WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_PROVIDER_SCHEMES = frozenset({"youtube", "spotify", "provider", "casu"})
_SECRET_QUERY_NAMES = frozenset(
    {"token", "access_token", "refresh_token", "key", "api_key", "signature", "sig", "password"}
)


class SourceLocationError(ValueError):
    pass


class SourceType(str, Enum):
    LOCAL_PATH = "local_path"
    FILE_URI = "file_uri"
    CONTENT_URI = "content_uri"
    NETWORK_URI = "network_uri"
    PROVIDER_LOCATOR = "provider_locator"


@dataclass(frozen=True, slots=True)
class SourceLocation:
    original: str
    canonical: str
    source_type: SourceType
    local_path: str | None = None


def classify_source(raw: str) -> SourceLocation:
    if not isinstance(raw, str) or not raw or len(raw) > MAX_SOURCE_CHARACTERS or "\0" in raw:
        raise SourceLocationError("invalid source text")
    if _WINDOWS_PATH.match(raw) or ":" not in raw:
        return SourceLocation(raw, raw, SourceType.LOCAL_PATH, raw)

    parsed = urlsplit(raw)
    scheme = parsed.scheme.lower()
    if scheme == "file":
        if parsed.netloc not in {"", "localhost"} or parsed.query or parsed.fragment:
            raise SourceLocationError("unsupported file URI authority or suffix")
        path = unquote(parsed.path)
        if not path or "\0" in path:
            raise SourceLocationError("invalid file URI path")
        return SourceLocation(raw, f"file://{quote(path, safe='/:%')}" , SourceType.FILE_URI, path)
    if scheme == "content":
        if not parsed.netloc or not parsed.path:
            raise SourceLocationError("invalid content URI")
        return SourceLocation(raw, urlunsplit((scheme, parsed.netloc, parsed.path, parsed.query, "")), SourceType.CONTENT_URI)
    if scheme in {"http", "https"}:
        if not parsed.hostname:
            raise SourceLocationError("invalid network URI")
        if parsed.username is not None or parsed.password is not None:
            raise SourceLocationError(f"network URI contains credentials: {redact_url(raw)}")
        host = parsed.hostname.lower()
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
        canonical = urlunsplit((scheme, host, parsed.path or "/", parsed.query, ""))
        return SourceLocation(raw, canonical, SourceType.NETWORK_URI)
    if scheme in _PROVIDER_SCHEMES and parsed.path:
        return SourceLocation(raw, f"{scheme}:{parsed.path}", SourceType.PROVIDER_LOCATOR)
    raise SourceLocationError(f"unsupported source scheme: {scheme!r}")


def redact_url(raw: str) -> str:
    """Remove userinfo and known secret query values from a URL."""
    try:
        parsed = urlsplit(raw)
        host = parsed.hostname or ""
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
        if parsed.username is not None or parsed.password is not None:
            host = f"[REDACTED]@{host}"
        query = urlencode(
            [
                (name, "[REDACTED]" if name.lower() in _SECRET_QUERY_NAMES else value)
                for name, value in parse_qsl(parsed.query, keep_blank_values=True)
            ]
        )
        return urlunsplit((parsed.scheme, host, parsed.path, query, ""))
    except (TypeError, ValueError):
        return "[INVALID_URL]"
