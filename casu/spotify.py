# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Spotify provider — honest, metadata-only integration.

Spotify streams are DRM/API-bound; yt-dlp has no Spotify extractor and this
product never pretends otherwise.  The provider therefore offers:

* URL recognition,
* public metadata lookup via Spotify's oEmbed endpoint (no credentials),
* an explicit, clearly labelled handoff to the YouTube provider
  ("Find on YouTube") using the fetched title.

What this module must NEVER do: search YouTube by opaque Spotify IDs, pass a
Spotify URL to yt-dlp as if it were resolvable, or label YouTube results as
Spotify streams.
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
    r"^(?:https?://)?(?:open\.)?spotify\.com/(track|album|playlist|episode)/([a-zA-Z0-9]{22})(?:\?.*)?$"
)

SPOTIFY_PLAYBACK_SUPPORTED = False


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


def spotify_playback_notice() -> str:
    return ("Spotify playback is not supported directly (Spotify streams are "
            "DRM/API-bound and yt-dlp has no Spotify extractor). Use "
            "“Find on YouTube” to search the track title on YouTube instead — "
            "the result is a YouTube stream, not a Spotify stream.")


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
            "blocked on this network; use the YouTube view's search with the "
            "track title instead") from exc
    title = str(data.get("title") or "").strip()
    if not title:
        raise SpotifyError("Spotify returned no title for this URL")
    return SpotifyMetadata(kind=match.group(1), title=title[:300], url=clean)


def youtube_handoff_query(metadata: SpotifyMetadata) -> str:
    """The honest handoff: search YouTube for the fetched human title."""
    return metadata.title


def spotdl_binary() -> str | None:
    """Locate spotDL (system PATH first, then the product venv)."""
    found = shutil.which("spotdl")
    if found:
        return found
    venv = "/opt/casu-spotdl/bin/spotdl"
    return venv if os.path.exists(venv) else None


def resolve_spotify_url(url: str, *, timeout: float = 60.0) -> str:
    """Resolve a Spotify URL to a playable stream via spotDL.

    spotDL is the legitimate Spotify provider: it reads Spotify metadata via
    the Spotify Web API and matches the track on YouTube, returning a stream
    URL without writing downloads to disk (``spotdl url``).  Credentials, if
    desired, come only from spotdl's own environment/configuration
    (SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET); nothing is embedded here.

    Without spotdl, or on networks where api.spotify.com is unreachable, this
    fails with a clear SpotifyError; the UI then offers the explicit
    "Find on YouTube" handoff instead of pretending anything else.
    """
    if not is_spotify_url(url):
        raise SpotifyError("Invalid Spotify URL")
    binary = spotdl_binary()
    if not binary:
        raise SpotifyError(
            "spotDL is not installed — install it (e.g. python3 -m venv "
            "/opt/casu-spotdl && /opt/casu-spotdl/bin/pip install spotdl) or "
            "use the explicit “Find on YouTube” handoff in the Spotify view")
    try:
        proc = subprocess.run([binary, "url", url.strip()], check=False,
                              text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              timeout=max(10.0, float(timeout)))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SpotifyError(f"spotDL execution failed: {exc}") from exc
    for line in reversed(proc.stdout.splitlines()):
        candidate = line.strip()
        if candidate.startswith(("http://", "https://")):
            return candidate
    detail = (proc.stderr or proc.stdout).strip().splitlines()
    raise SpotifyError(
        f"spotDL could not resolve this Spotify URL"
        f"{': ' + detail[-1][:200] if detail else ''} — api.spotify.com may be "
        "blocked on this network; use the “Find on YouTube” handoff instead")
