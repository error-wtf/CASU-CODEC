# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Provider semantics regression tests.

Spotify and YouTube must never be silently mixed: no Spotify URL may reach
yt-dlp, no YouTube result may be labelled Spotify, and the Spotify provider
is metadata-only with an explicit YouTube handoff.
"""
from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest

from casu.locations import LocationResolutionError, resolve_media_location
from casu.search import search_music, search_youtube
from casu.spotify import (SpotifyError, fetch_spotify_metadata, is_spotify_url,
                          spotify_playback_notice, youtube_handoff_query)

SPOTIFY_URL = "https://open.spotify.com/track/0VjIjW4GlUZAMYB2vXMi3b"


def test_spotify_url_never_reaches_ytdlp(monkeypatch):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append(args)
        raise AssertionError("subprocess must not run without spotDL")

    import subprocess
    monkeypatch.setattr(subprocess, "run", fake_run)
    import casu.spotify as spotify_mod
    monkeypatch.setattr(spotify_mod, "spotdl_binary", lambda: None)
    with pytest.raises(LocationResolutionError) as exc:
        resolve_media_location(SPOTIFY_URL)
    assert "spotDL" in str(exc.value)
    assert calls == []


def test_spotify_resolution_uses_spotdl_provider(tmp_path, monkeypatch):
    fake = tmp_path / "spotdl"
    fake.write_text("#!/bin/sh\necho 'https://example.com/yt-stream'\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{__import__('os').environ['PATH']}")
    resolved = resolve_media_location(SPOTIFY_URL)
    assert resolved == "https://example.com/yt-stream"


def test_spotify_provider_is_metadata_only():
    assert "not supported" in spotify_playback_notice()
    assert "YouTube" in spotify_playback_notice()


def test_fetch_spotify_metadata_parses_oembed(monkeypatch):
    payload = json.dumps({"title": "Fehler im System", "type": "track"}).encode()

    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout=None):
        assert "open.spotify.com/oembed" in request.full_url
        return FakeResponse(payload)

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    meta = fetch_spotify_metadata(SPOTIFY_URL)
    assert meta.title == "Fehler im System"
    assert meta.kind == "track"
    assert youtube_handoff_query(meta) == "Fehler im System"


def test_fetch_spotify_metadata_rejects_invalid_url():
    with pytest.raises(SpotifyError):
        fetch_spotify_metadata("https://example.com/not-spotify")


def test_search_results_are_never_labelled_spotify(tmp_path, monkeypatch):
    entry = json.dumps({"id": "vid0", "title": "T", "url":
                        "https://www.youtube.com/watch?v=vid0",
                        "duration": 10, "uploader": "U"}) + "\n"
    script = tmp_path / "yt-dlp"
    script.write_text(f"#!/bin/sh\ncat <<'EOF'\n{entry}EOF\n")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{__import__('os').environ['PATH']}")
    for engine in (search_youtube, search_music):
        results = engine("x", limit=1)
        assert results[0].source == "youtube"


def test_is_spotify_url_recognition():
    assert is_spotify_url(SPOTIFY_URL)
    assert not is_spotify_url("https://www.youtube.com/watch?v=vid0")
