# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Spotify provider via spotDL.

MPCASU never touches Spotify's DRM/API-bound streams directly.  Instead it
uses spotDL, which reads Spotify metadata through the Spotify Web API and
matches each track to an audio source at an open provider (usually YouTube).
The playable audio is therefore a spotDL-matched external source, never a
Spotify stream.  The UI always labels it that way.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from dataclasses import dataclass

SPOTIFY_TRACK_RE = re.compile(
    r"^(?:https?://)?open\.spotify\.com/(track|album|playlist|episode|show|artist)/([a-zA-Z0-9]{22})(?:\?.*)?$"
)


class SpotifyError(ValueError):
    pass


@dataclass(frozen=True)
class SpotifyMetadata:
    kind: str
    title: str
    url: str


def is_spotify_url(url: str) -> bool:
    return bool(SPOTIFY_TRACK_RE.match((url or "").strip()))


def spotify_id(url: str) -> str | None:
    match = SPOTIFY_TRACK_RE.match((url or "").strip())
    return match.group(2) if match else None


def fetch_spotify_metadata(url: str, *, timeout: float = 15.0) -> SpotifyMetadata:
    """Fetch public oEmbed metadata (title/kind) for a Spotify URL.

    Requires open.spotify.com to be reachable; on blocked networks this fails
    with a clear SpotifyError instead of fake data.
    """
    clean = (url or "").strip()
    match = SPOTIFY_TRACK_RE.match(clean)
    if not match:
        raise SpotifyError("Invalid Spotify URL")
    if not clean.startswith("http"):
        clean = "https://" + clean
    endpoint = "https://open.spotify.com/oembed?url=" + urllib.parse.quote(clean, safe="")
    request = urllib.request.Request(endpoint, headers={"User-Agent": "MPCASU/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=max(3.0, float(timeout))) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise SpotifyError(
            f"Spotify metadata fetch failed: {exc} — open.spotify.com may be "
            "blocked on this network") from exc
    title = str(data.get("title") or "").strip()
    if not title:
        raise SpotifyError("Spotify returned no title for this URL")
    return SpotifyMetadata(kind=match.group(1), title=title[:300], url=clean)


def youtube_handoff_query(metadata: SpotifyMetadata) -> str:
    """Search YouTube for the fetched human title (explicit handoff)."""
    return metadata.title


@dataclass(frozen=True)
class SpotifySearchResult:
    title: str
    artist: str
    url: str
    duration: float | None = None


def spotdl_binary() -> str | None:
    """Locate spotDL (system PATH first, then the product venv)."""
    found = shutil.which("spotdl")
    if found:
        return found
    venv = "/opt/casu-spotdl/bin/spotdl"
    return venv if os.path.exists(venv) else None


def spotify_kind(url: str) -> str | None:
    """Return the resource kind (track/album/playlist/...) or None."""
    match = SPOTIFY_TRACK_RE.match((url or "").strip())
    return match.group(1) if match else None


def _spotdl_save(query: str, *, timeout: float) -> list[SpotifySearchResult]:
    """Run ``spotdl save QUERY --save-file -`` and parse the JSON song array."""
    binary = spotdl_binary()

    if not binary:
        raise SpotifyError("spotDL is not installed")

    try:
        proc = subprocess.run(
            [
                binary,
                "save",
                query,
                "--save-file",
                "-",
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(10.0, float(timeout)),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SpotifyError(f"spotDL search failed: {exc}") from exc

    if proc.returncode:
        detail = proc.stderr.strip().splitlines()
        raise SpotifyError(
            detail[-1][:300] if detail
            else "spotDL search failed"
        )

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SpotifyError(
            "spotDL returned invalid JSON"
        ) from exc

    if isinstance(payload, dict):
        payload = payload.get("songs", [])

    if not isinstance(payload, list):
        raise SpotifyError(
            "spotDL returned an unexpected save document"
        )

    results = []

    for data in payload:
        if not isinstance(data, dict):
            continue

        url = str(
            data.get("url")
            or data.get("spotify_url")
            or ""
        ).strip()

        if "spotify.com/" not in url:
            continue

        artists = data.get("artists") or data.get("artist") or []

        if isinstance(artists, str):
            artist = artists
        elif isinstance(artists, list):
            names = []
            for value in artists:
                if isinstance(value, dict):
                    name = str(value.get("name") or "")
                    if name:
                        names.append(name)
                elif value is not None:
                    names.append(str(value))
            artist = ", ".join(names)
        else:
            artist = ""

        duration = data.get("duration")

        try:
            duration = float(duration) if duration is not None else None
        except (TypeError, ValueError):
            duration = None

        results.append(
            SpotifySearchResult(
                title=str(
                    data.get("name")
                    or data.get("title")
                    or "Spotify track"
                )[:300],
                artist=artist[:200],
                url=url,
                duration=duration,
            )
        )

    return results


def search_spotify(query: str, *, limit: int = 12,
                   timeout: float = 90.0) -> list[SpotifySearchResult]:
    """Search Spotify via spotDL (metadata only, no audio downloads).

    Runs ``spotdl save QUERY --save-file -`` and parses the JSON song array
    spotDL writes to stdout.  Returns results carrying the real Spotify track
    URLs.  Requires spotDL and a reachable Spotify API.
    """
    query = (query or "").strip()

    if not query:
        raise SpotifyError("search query must not be empty")

    results = _spotdl_save(query, timeout=timeout)

    if not results:
        raise SpotifyError("spotDL found no Spotify results")

    return results[:max(1, min(int(limit), 25))]


def expand_spotify(url: str, *, limit: int = 100,
                   timeout: float = 120.0) -> list[SpotifySearchResult]:
    """Expand a Spotify album/playlist (or single track) into its tracks.

    Uses the same ``spotdl save <url> --save-file -`` interface, which returns
    one song entry per track.  Artists, episodes and shows cannot be expanded
    to a playable track list and raise SpotifyError.
    """
    clean = (url or "").strip()
    kind = spotify_kind(clean)

    if not kind:
        raise SpotifyError("Invalid Spotify URL")

    if kind not in ("track", "album", "playlist"):
        raise SpotifyError(
            f"Spotify {kind} cannot be expanded into tracks before playback")

    results = _spotdl_save(clean, timeout=timeout)

    if not results:
        raise SpotifyError("spotDL found no Spotify results")

    return results[:max(1, min(int(limit), 200))]


def resolve_spotify_url(url: str, *, timeout: float = 60.0) -> str:
    """Resolve a Spotify TRACK to a matched playable audio URL via spotDL.

    Only single tracks are supported here.  Albums, playlists and artists must
    be expanded into their individual tracks before playback; the UI queues
    those individually instead of pretending a group is one song.
    """
    clean = (url or "").strip()
    match = SPOTIFY_TRACK_RE.match(clean)

    if not match:
        raise SpotifyError("Invalid Spotify URL")

    kind = match.group(1)

    if kind != "track":
        raise SpotifyError(
            f"Spotify {kind} must be expanded into tracks before playback"
        )

    binary = spotdl_binary()

    if not binary:
        raise SpotifyError("spotDL is not installed")

    try:
        proc = subprocess.run(
            [binary, "url", clean],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(10.0, float(timeout)),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SpotifyError(
            f"spotDL execution failed: {exc}"
        ) from exc

    urls = [
        line.strip()
        for line in proc.stdout.splitlines()
        if line.strip().startswith(("http://", "https://"))
    ]

    if proc.returncode or not urls:
        detail = proc.stderr.strip().splitlines()
        raise SpotifyError(
            detail[-1][:300]
            if detail
            else "spotDL returned no playable URL"
        )

    return urls[0]
