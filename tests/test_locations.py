from __future__ import annotations

import subprocess

import pytest

from casu.locations import (LocationResolutionError, is_youtube_url,
                            resolve_media_location)


def test_direct_stream_location_is_not_rewritten():
    url = "https://radio.example/live/stream.m3u8"
    assert resolve_media_location(url) == url
    assert not is_youtube_url(url)


def test_youtube_location_resolves_one_combined_http_stream(monkeypatch):
    monkeypatch.setattr("casu.locations.shutil.which", lambda _name: "/usr/bin/yt-dlp")
    monkeypatch.setattr("casu.locations.subprocess.run", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args[0], 0,
                                                    "https://media.example/video.mp4\n", ""))
    assert resolve_media_location("https://youtu.be/abc") == "https://media.example/video.mp4"


def test_youtube_location_fails_without_resolver(monkeypatch):
    monkeypatch.setattr("casu.locations.shutil.which", lambda _name: None)
    with pytest.raises(LocationResolutionError, match="requires yt-dlp"):
        resolve_media_location("https://www.youtube.com/watch?v=abc")


def test_youtube_location_rejects_split_or_invalid_results(monkeypatch):
    monkeypatch.setattr("casu.locations.shutil.which", lambda _name: "/usr/bin/yt-dlp")
    monkeypatch.setattr("casu.locations.subprocess.run", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args[0], 0,
                                                    "https://a/video\nhttps://a/audio\n", ""))
    with pytest.raises(LocationResolutionError, match="no playable combined"):
        resolve_media_location("https://youtube.com/watch?v=abc")

