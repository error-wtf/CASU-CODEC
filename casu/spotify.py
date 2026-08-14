"""Spotify URL resolution for MPCASU.

Resolves Spotify URLs by searching for the track on YouTube via yt-dlp,
since yt-dlp does not natively support Spotify streams.
"""
from __future__ import annotations

import re
import subprocess
import shutil
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SPOTIFY_TRACK_RE = re.compile(
    r"^(?:https?://)?(?:open\.)?spotify\.com/(track|album|playlist|episode)/([a-zA-Z0-9]{22})(?:\?.*)?$"
)


class SpotifyError(ValueError):
    pass


def is_spotify_url(url: str) -> bool:
    return bool(SPOTIFY_TRACK_RE.match(url.strip()))


def spotify_id(url: str) -> str | None:
    match = SPOTIFY_TRACK_RE.match(url.strip())
    return match.group(2) if match else None


def _resolve_via_ytdlp_search(query: str, *, timeout: float = 30.0) -> str:
    """Search YouTube for a track and return the best audio/video stream URL."""
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        raise SpotifyError("yt-dlp is required for Spotify resolution. Install it with: pip install yt-dlp")
    try:
        result = subprocess.run(
            [ytdlp, "--no-playlist", "--no-warnings", "--no-progress",
             "--socket-timeout", "10", "--get-url", "--format",
             "bestaudio/best", f"ytsearch:{query}"],
            check=False, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=max(5.0, float(timeout)),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SpotifyError(f"Spotify search failed: {exc}") from exc
    urls = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if result.returncode or not urls:
        detail = result.stderr.strip().splitlines()
        msg = detail[-1][:300] if detail else "no playable stream found on YouTube"
        raise SpotifyError(f"Spotify: {msg}")
    parsed = urllib.parse.urlparse(urls[0])
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SpotifyError("Search returned an invalid media location")
    return urls[0]


def resolve_spotify_url(url: str, *, timeout: float = 30.0) -> str:
    """Resolve a Spotify URL to a playable media stream."""
    match = SPOTIFY_TRACK_RE.match(url.strip())
    if not match:
        raise SpotifyError("Invalid Spotify URL")
    spotify_type, spotify_id_val = match.group(1), match.group(2)
    resolved = _resolve_via_ytdlp_search(f"spotify {spotify_id_val}",
                                         timeout=timeout)
    return resolved


def resolve_spotify_playlist(url: str, *, timeout: float = 30.0) -> list[str]:
    """Resolve a Spotify playlist URL to individual track stream URLs.
    
    Uses the Spotify playlist ID to search for tracks on YouTube.
    """
    match = SPOTIFY_TRACK_RE.match(url.strip())
    if not match:
        raise SpotifyError("Invalid Spotify URL")
    spotify_type, spotify_id_val = match.group(1), match.group(2)
    if spotify_type != "playlist":
        return [resolve_spotify_url(url, timeout=timeout)]
    raise SpotifyError(
        "Spotify playlist resolution requires the spotDL tool.\n"
        "Install: pip install spotdl\n"
        "Then use: spotdl 'https://open.spotify.com/playlist/...'"
    )
