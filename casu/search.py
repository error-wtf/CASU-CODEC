# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""YouTube search via yt-dlp with structured, bounded results.

All search in this product runs against the YouTube index; the music variant
is a convenience preset for music queries.  Results are always labelled with
their real provider ("youtube") — never as Spotify.  Spotify remains a
separate metadata-only provider (casu.spotify) with an explicit "Find on
YouTube" handoff.  Results are metadata only — playback resolves each entry
on demand and never writes downloads to disk.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass

MAX_SEARCH_LIMIT = 25
DEFAULT_TIMEOUT = 30.0


class SearchError(ValueError):
    pass


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    duration: float | None
    uploader: str
    source: str

    def as_dict(self) -> dict:
        return asdict(self)


def _run_ytdlp_search(query: str, limit: int, timeout: float) -> list[dict]:
    executable = shutil.which("yt-dlp")
    if not executable:
        raise SearchError("search requires yt-dlp (Debian package: yt-dlp)")
    limit = max(1, min(int(limit), MAX_SEARCH_LIMIT))
    command = [executable, "--no-warnings", "--flat-playlist", "--dump-json",
               "--socket-timeout", "10", f"ytsearch{limit}:{query}"]
    try:
        proc = subprocess.run(command, check=False, text=True,
                              capture_output=True,
                              timeout=max(5.0, float(timeout)))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SearchError(f"search failed: {exc}") from exc
    entries: list[dict] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    if not entries:
        detail = proc.stderr.strip().splitlines()
        raise SearchError(detail[-1][:300] if detail else "no results found")
    return entries


def _to_results(entries: list[dict], source: str, limit: int) -> list[SearchResult]:
    results: list[SearchResult] = []
    for entry in entries:
        video_id = str(entry.get("id") or "")
        url = str(entry.get("url") or "")
        if not url and video_id:
            url = f"https://www.youtube.com/watch?v={video_id}"
        if not url:
            continue
        duration = entry.get("duration")
        try:
            duration = float(duration) if duration is not None else None
        except (TypeError, ValueError):
            duration = None
        results.append(SearchResult(
            title=str(entry.get("title") or video_id or url)[:300],
            url=url,
            duration=duration,
            uploader=str(entry.get("uploader") or entry.get("channel") or "")[:200],
            source=source))
        if len(results) >= limit:
            break
    if not results:
        raise SearchError("search returned no usable entries")
    return results


def search_youtube(query: str, *, limit: int = 12,
                   timeout: float = DEFAULT_TIMEOUT) -> list[SearchResult]:
    """Search YouTube videos; returns at most `limit` structured results."""
    query = (query or "").strip()
    if not query:
        raise SearchError("search query must not be empty")
    return _to_results(_run_ytdlp_search(query, limit, timeout), "youtube", limit)


def search_music(query: str, *, limit: int = 12,
                 timeout: float = DEFAULT_TIMEOUT) -> list[SearchResult]:
    """Music-oriented YouTube search preset (results labelled "youtube")."""
    query = (query or "").strip()
    if not query:
        raise SearchError("search query must not be empty")
    return _to_results(_run_ytdlp_search(query, limit, timeout), "youtube", limit)
