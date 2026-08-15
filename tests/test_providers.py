# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Provider semantics regression tests.

YouTube uses yt-dlp; Spotify uses spotDL (Spotify metadata matched to an
open audio provider).  The two providers must never be silently mixed: no
YouTube result may be labelled Spotify and no Spotify track is treated as a
downloadable Spotify stream.
"""
from __future__ import annotations

import io
import json
import os
from types import SimpleNamespace

import pytest

from casu.locations import LocationResolutionError, resolve_media_location
from casu.search import search_music, search_youtube
from casu.spotify import (SpotifyError, expand_spotify, fetch_spotify_metadata,
                          is_spotify_url, resolve_spotify_url, search_spotify,
                          spotify_kind, youtube_handoff_query)

SPOTIFY_URL = "https://open.spotify.com/track/0VjIjW4GlUZAMYB2vXMi3b"


def _fake_spotdl(tmp_path, monkeypatch, stdout_text):
    script = tmp_path / "spotdl"
    script.write_text(
        f"#!/bin/sh\n"
        f"# write the JSON payload to --save-file <path> (or stdout fallback)\n"
        f"out=\n"
        f"while [ $# -gt 0 ]; do\n"
        f"  if [ \"$1\" = --save-file ]; then shift; out=\"$1\"; fi\n"
        f"  shift\n"
        f"done\n"
        f"if [ -n \"$out\" ]; then\n"
        f"  printf '%s' '{stdout_text}' > \"$out\"\n"
        f"else\n"
        f"  cat <<'EOF'\n{stdout_text}\nEOF\n"
        f"fi\n")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")


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
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    resolved = resolve_media_location(SPOTIFY_URL)
    assert resolved == "https://example.com/yt-stream"


def test_spotify_search_uses_documented_save_interface(tmp_path, monkeypatch):
    payload = json.dumps([{
        "name": "Blinding Lights",
        "artists": [{"name": "The Weeknd"}],
        "url": "https://open.spotify.com/track/0VjIjW4GlUZAMYB2vXMi3b",
        "duration": 200.0,
    }])
    script = tmp_path / "spotdl"
    script.write_text(
        f"#!/bin/sh\ntest \"$1\" = save || exit 99\n"
        f"test \"$3\" = --save-file || exit 98\n"
        f"printf '%s' '{payload}' > \"$4\"\n")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    results = search_spotify("The Weeknd Blinding Lights", limit=5)
    assert len(results) == 1
    assert results[0].title == "Blinding Lights"
    assert results[0].artist == "The Weeknd"
    assert results[0].url == "https://open.spotify.com/track/0VjIjW4GlUZAMYB2vXMi3b"
    assert results[0].duration == 200.0


def test_spotify_search_accepts_plain_artist_strings(tmp_path, monkeypatch):
    payload = json.dumps([{
        "name": "Zusammenspiel",
        "artist": "ERROR.WTF",
        "url": "https://open.spotify.com/track/1x2y3z4w5v6a7b8c9d0e1f2",
        "duration": None,
    }])
    _fake_spotdl(tmp_path, monkeypatch, payload)
    results = search_spotify("error wtf", limit=3)
    assert results[0].artist == "ERROR.WTF"
    assert results[0].duration is None


def test_spotify_search_rejects_non_list_document(tmp_path, monkeypatch):
    _fake_spotdl(tmp_path, monkeypatch, "42")
    with pytest.raises(SpotifyError, match="unexpected save document"):
        search_spotify("x", limit=3)


def test_spotify_resolution_rejects_non_track():
    for url in (
        "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
        "https://open.spotify.com/album/1DFixLWuPkv3KT3TnV35m3",
        "https://open.spotify.com/artist/6qqNVTkY8uBg9cPqJd7KUm",
    ):
        with pytest.raises(SpotifyError, match="expanded into tracks"):
            resolve_spotify_url(url)


def test_spotify_track_resolution_takes_first_url(tmp_path, monkeypatch):
    script = tmp_path / "spotdl"
    script.write_text(
        "#!/bin/sh\nprintf '%s\\n' 'debug line'\n"
        "echo 'https://example.com/matched-audio'\n"
        "echo 'https://example.com/ignored'\n")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    resolved = resolve_spotify_url(SPOTIFY_URL)
    assert resolved == "https://example.com/matched-audio"


def test_spotify_playlist_expands_to_tracks(tmp_path, monkeypatch):
    payload = json.dumps([
        {"name": "Track One", "artists": ["A"], "duration": 120,
         "url": "https://open.spotify.com/track/1x1x1x1x1x1x1x1x1x1x1x1x1x1"},
        {"name": "Track Two", "artists": [{"name": "B"}], "duration": 240,
         "url": "https://open.spotify.com/track/2y2y2y2y2y2y2y2y2y2y2y2y2y2"},
    ])
    _fake_spotdl(tmp_path, monkeypatch, payload)
    results = expand_spotify(
        "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M")
    assert len(results) == 2
    assert results[0].title == "Track One"
    assert results[0].url.startswith("https://open.spotify.com/track/")
    assert results[1].artist == "B"


def test_spotify_artist_expansion_is_rejected():
    with pytest.raises(SpotifyError, match="cannot be expanded"):
        expand_spotify(
            "https://open.spotify.com/artist/6qqNVTkY8uBg9cPqJd7KUm")


def test_spotify_kind_classification():
    assert spotify_kind(SPOTIFY_URL) == "track"
    assert spotify_kind(
        "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M") == "playlist"
    assert spotify_kind("https://example.com/not-spotify") is None


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
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    for engine in (search_youtube, search_music):
        results = engine("x", limit=1)
        assert results[0].source == "youtube"


def test_is_spotify_url_recognition():
    assert is_spotify_url(SPOTIFY_URL)
    assert not is_spotify_url("https://www.youtube.com/watch?v=vid0")
