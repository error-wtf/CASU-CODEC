"""Bounded playlist model shared by MPCASU queue presentations.

Supports JSON, M3U, Extended M3U and PLS playlist formats with
content-based auto-detection.
"""
from __future__ import annotations

import re
import urllib.parse
from pathlib import Path
from typing import Iterable

from .core import CasuError
from .fileio import atomic_write_json, read_bounded_json


MAX_PLAYLIST_ITEMS = 10_000
MAX_PLAYLIST_PATH_BYTES = 4096
MAX_PLAYLIST_FILE_BYTES = 8 * 1024 * 1024
MAX_LINE_BYTES = 4096


class PlaylistError(ValueError):
    pass


def _bounded_text(value: str, label: str, maximum: int = MAX_PLAYLIST_PATH_BYTES) -> str:
    text = str(value).strip()
    if "\0" in text or len(text.encode("utf-8")) > maximum:
        raise PlaylistError(f"{label} exceeds safety limit")
    return text


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("iso-8859-1")


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
        if not text or "\0" in text or len(text.encode("utf-8")) > MAX_PLAYLIST_PATH_BYTES:
            raise PlaylistError("playlist path is invalid")
        return Path(text).expanduser().resolve()

    def add(self, values: Iterable, *, existing_only: bool = False) -> int:
        """Add items (Path or str URLs) to playlist."""
        added = 0
        known = {str(item) for item in self._items}
        for value in values:
            if isinstance(value, str) and self._is_url(value):
                if value in known:
                    continue
                if len(self._items) >= MAX_PLAYLIST_ITEMS:
                    raise PlaylistError("playlist item count exceeds limit")
                self._items.append(value)
                known.add(value)
                added += 1
            else:
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

    @staticmethod
    def _is_url(value: str) -> bool:
        try:
            parsed = urllib.parse.urlparse(value)
            return bool(parsed.scheme and parsed.netloc)
        except ValueError:
            return False

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


def detect_playlist_format(path: str | Path) -> str:
    """Detect playlist format by content: json, m3u, pls, or unknown."""
    source = Path(path).expanduser().resolve()
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise PlaylistError(f"could not read playlist: {exc}") from exc
    if len(raw) > MAX_PLAYLIST_FILE_BYTES:
        raise PlaylistError("playlist exceeds safety limit")
    text = raw.lstrip()
    if text.startswith(b"{"):
        return "json"
    if text.startswith(b"#EXTM3U") or text.startswith(b"#EXTINF"):
        return "m3u"
    if text.startswith(b"[playlist]"):
        return "pls"
    line = text.split(b"\n", 1)[0].strip()
    if b"File1=" in line:
        return "pls"
    return "unknown"


def m3u_names(text: str) -> dict:
    """Map stream/file URLs to their #EXTINF display names (best effort)."""
    names: dict = {}
    pending: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            comma = line.find(",")
            pending = line[comma + 1:].strip() if comma >= 0 else None
            continue
        if line.startswith("#"):
            continue
        if pending:
            names[line] = pending[:300]
        pending = None
    return names


def pls_names(text: str) -> dict:
    """Map FileN= entries to TitleN= display names (best effort)."""
    files: dict = {}
    titles: dict = {}
    for raw in text.splitlines():
        line = raw.strip()
        mfile = re.match(r"^File(\d+)=(.*)$", line) if line else None
        mtitle = re.match(r"^Title(\d+)=(.*)$", line) if line else None
        if mfile:
            files[int(mfile.group(1))] = mfile.group(2).strip()
        elif mtitle:
            titles[int(mtitle.group(1))] = mtitle.group(2).strip()[:300]
    return {url: titles[idx] for idx, url in files.items() if idx in titles}


def playlist_names(path: str | Path) -> dict:
    """Display names for playlist entries, by extension (empty on failure)."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    ext = Path(path).suffix.lower()
    if ext in {".m3u", ".m3u8"}:
        return m3u_names(text)
    if ext == ".pls":
        return pls_names(text)
    return {}


def _parse_m3u_text(text: str, base: Path | None = None) -> list:
    """Parse M3U playlist. Returns list of Path (local files) and str (stream URLs)."""
    lines = text.splitlines()
    if any(len(line.encode("utf-8")) > MAX_LINE_BYTES for line in lines):
        raise PlaylistError("playlist line exceeds safety limit")
    items: list = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            parsed = urllib.parse.urlparse(line)
            if parsed.scheme and parsed.netloc:
                # This is a stream URL - keep it as string
                items.append(_bounded_text(line, "stream URL"))
                continue
        except ValueError:
            pass
        candidate = Path(line)
        if not candidate.is_absolute() and base is not None:
            candidate = base / candidate
        items.append(Path(candidate).expanduser().resolve())
    return items


def _parse_pls_text(text: str, base: Path | None = None) -> list[Path]:
    paths: list[Path] = []
    for match in re.finditer(r"^File\d+\s*=\s*(.+)$", text, re.MULTILINE | re.IGNORECASE):
        raw = match.group(1).strip()
        candidate = Path(raw)
        if not candidate.is_absolute() and base is not None:
            candidate = base / candidate
        paths.append(_bounded_text(str(candidate), "playlist entry"))
    return [Path(p).expanduser().resolve() for p in paths]


def parse_m3u(raw: bytes, base: Path | None = None) -> list[Path]:
    return _parse_m3u_text(_decode(raw), base)


def parse_pls(raw: bytes, base: Path | None = None) -> list[Path]:
    return _parse_pls_text(_decode(raw), base)


def _read_bytes(path: str | Path) -> bytes:
    source = Path(path).expanduser().resolve()
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise PlaylistError(f"could not read playlist: {exc}") from exc
    if len(raw) > MAX_PLAYLIST_FILE_BYTES:
        raise PlaylistError("playlist exceeds safety limit")
    return raw


def load_playlist_file(path: str | Path, *, existing_only: bool = False) -> PlaylistModel:
    source = Path(path).expanduser().resolve()
    ext = source.suffix.lower()
    if ext == ".json":
        try:
            payload = read_bounded_json(source, max_bytes=MAX_PLAYLIST_FILE_BYTES,
                                        label="playlist document")
            return PlaylistModel.from_payload(payload, existing_only=existing_only)
        except CasuError as exc:
            raise PlaylistError(str(exc)) from exc
    fmt = detect_playlist_format(source)
    raw = _read_bytes(source)
    if fmt == "m3u":
        paths = parse_m3u(raw, base=source.parent)
    elif fmt == "pls":
        paths = parse_pls(raw, base=source.parent)
    else:
        raise PlaylistError(f"unknown playlist format: {source.suffix}")
    result = PlaylistModel()
    result.add(paths, existing_only=existing_only)
    return result


def save_playlist_file(path: str | Path, model: PlaylistModel) -> Path:
    target = Path(path).expanduser().resolve()
    suffix = target.suffix.lower()
    if suffix in {".m3u", ".m3u8"}:
        lines = ["#EXTM3U", ""]
        for item in model.items:
            lines.append(str(item))
        text = "\n".join(lines) + "\n"
        if len(text.encode("utf-8")) > MAX_PLAYLIST_FILE_BYTES:
            raise PlaylistError("playlist exceeds safety limit")
        target.write_text(text, encoding="utf-8")
        return target
    if suffix == ".pls":
        lines = ["[playlist]", f"NumberOfEntries={len(model.items)}", ""]
        for index, item in enumerate(model.items, 1):
            lines.append(f"File{index}={item}")
            lines.append(f"Title{index}={item.name}")
        lines.append("Version=2")
        text = "\n".join(lines) + "\n"
        if len(text.encode("utf-8")) > MAX_PLAYLIST_FILE_BYTES:
            raise PlaylistError("playlist exceeds safety limit")
        target.write_text(text, encoding="utf-8")
        return target
    try:
        return atomic_write_json(target, model.to_payload(), max_bytes=MAX_PLAYLIST_FILE_BYTES)
    except CasuError as exc:
        raise PlaylistError(str(exc)) from exc


def detect_media_type(path: str | Path) -> str:
    """Quick media-type label for display (does not probe content)."""
    source = Path(path).expanduser().resolve()
    ext = source.suffix.lower().lstrip(".")
    if ext in {"mp3", "flac", "wav", "aac", "ogg", "opus", "m4a", "wma",
               "aiff", "alac", "ape", "wv", "tta", "dts", "mpc", "voc", "au"}:
        return ext.upper()
    if ext in {"mp4", "mkv", "webm", "avi", "mov", "m4v", "flv", "wmv",
               "mpeg", "mpg", "m2ts", "mts", "ts", "vob", "ogv", "3gp",
               "divx", "rm", "rmvb", "mxf", "asf"}:
        return ext.upper()
    if ext in {"m3u", "m3u8", "pls"}:
        return "PLAYLIST"
    if ext in {"casu", "mp5"}:
        return "CASU"
    return "MEDIA"


def detect_entry_type(path: str | Path) -> str:
    """Classify a playlist entry as local file, stream URL, YouTube, CASU, etc."""
    source = str(path)
    from urllib.parse import urlparse
    try:
        parsed = urlparse(source)
        if parsed.scheme and parsed.netloc:
            host = parsed.hostname.lower() if parsed.hostname else ""
            if host in _YOUTUBE_HOSTS:
                return "youtube"
            if parsed.scheme in {"http", "https"}:
                return "http-stream"
            if parsed.scheme in {"rtsp", "rtsps"}:
                return "rtsp-stream"
            if parsed.scheme in {"rtmp", "rtmps"}:
                return "rtmp-stream"
            if parsed.scheme in {"mmsh", "mmst"}:
                return "mms-stream"
            if parsed.scheme in {"udp", "srt", "rist"}:
                return "udp-stream"
            if parsed.scheme == "ftp":
                return "ftp-stream"
            return "network-stream"
    except ValueError:
        pass
    suffix = Path(source).suffix.lower()
    if suffix == ".casu":
        return "casu"
    if suffix in {".mp5", ".mp5a"}:
        return "mp5"
    if suffix in {".m3u", ".m3u8", ".pls"}:
        return "playlist"
        from urllib.parse import urlparse
    try:
        parsed = urlparse(str(source))
        if parsed.hostname and "spotify.com" in parsed.hostname.lower():
            return "spotify"
    except ValueError:
        pass
    return "local-file"


_YOUTUBE_HOSTS = frozenset({
    "youtube.com", "www.youtube.com", "m.youtube.com",
    "music.youtube.com", "youtu.be", "www.youtu.be",
    "youtube-nocookie.com", "www.youtube-nocookie.com",
})
