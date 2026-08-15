# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Behavior tests for casu.search with a scripted yt-dlp stand-in."""
from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest

from casu import search as search_module
from casu.search import (MAX_SEARCH_LIMIT, SearchError, search_music,
                         search_youtube)


def _fake_ytdlp(tmp_path: Path, stdout: str, returncode: int = 0,
                stderr: str = "") -> Path:
    script = tmp_path / "yt-dlp"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        f"sys.stdout.write({json.dumps(stdout)})\n"
        f"sys.stderr.write({json.dumps(stderr)})\n"
        f"sys.exit({returncode})\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def _entries(count: int = 3) -> str:
    lines = []
    for index in range(count):
        lines.append(json.dumps({
            "id": f"vid{index}",
            "url": f"https://www.youtube.com/watch?v=vid{index}",
            "title": f"Result {index}",
            "duration": 60 + index,
            "uploader": f"Channel {index}",
        }))
    return "\n".join(lines) + "\n"


def test_search_youtube_structured_results(tmp_path, monkeypatch):
    _fake_ytdlp(tmp_path, _entries(3))
    monkeypatch.setenv("PATH", f"{tmp_path}:{__import__('os').environ['PATH']}")
    results = search_youtube("lino casu", limit=5)
    assert len(results) == 3
    first = results[0]
    assert first.title == "Result 0"
    assert first.url == "https://www.youtube.com/watch?v=vid0"
    assert first.duration == 60.0
    assert first.uploader == "Channel 0"
    assert first.source == "youtube"
    assert first.as_dict()["title"] == "Result 0"


def test_search_music_never_labels_results_as_spotify(tmp_path, monkeypatch):
    """Provider semantics must not be mixed: music search is YouTube search."""
    _fake_ytdlp(tmp_path, _entries(1))
    monkeypatch.setenv("PATH", f"{tmp_path}:{__import__('os').environ['PATH']}")
    results = search_music("error wtf", limit=3)
    assert results[0].source == "youtube"


def test_search_entries_without_url_get_canonical_link(tmp_path, monkeypatch):
    payload = json.dumps({"id": "abc123", "title": "Only id"}) + "\n"
    _fake_ytdlp(tmp_path, payload)
    monkeypatch.setenv("PATH", f"{tmp_path}:{__import__('os').environ['PATH']}")
    results = search_youtube("x")
    assert results[0].url == "https://www.youtube.com/watch?v=abc123"
    assert results[0].duration is None


def test_youtube_playlist_expands_to_videos(tmp_path, monkeypatch):
    entries = "\n".join(json.dumps({
        "id": f"vid{i}", "title": f"Video {i}", "duration": 60 + i,
        "uploader": "Channel",
    }) for i in range(3)) + "\n"
    script = tmp_path / "yt-dlp"
    script.write_text(
        "#!/bin/sh\ntest \"$1\" = --flat-playlist || exit 99\n"
        f"cat <<'EOF'\n{entries}EOF\n")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{__import__('os').environ['PATH']}")
    from casu.search import search_youtube_playlist
    results = search_youtube_playlist(
        "https://www.youtube.com/playlist?list=PLabc123", limit=5)
    assert len(results) == 3
    assert results[0].url == "https://www.youtube.com/watch?v=vid0"
    assert all(item.source == "youtube" for item in results)


def test_search_empty_query_rejected():
    with pytest.raises(SearchError, match="empty"):
        search_youtube("   ")
    with pytest.raises(SearchError, match="empty"):
        search_music("")


def test_search_no_results_maps_stderr(tmp_path, monkeypatch):
    _fake_ytdlp(tmp_path, "", returncode=1, stderr="boom: nothing found\n")
    monkeypatch.setenv("PATH", f"{tmp_path}:{__import__('os').environ['PATH']}")
    with pytest.raises(SearchError, match="boom"):
        search_youtube("nonexistent")


def test_search_missing_ytdlp_raises(monkeypatch):
    monkeypatch.setattr(search_module.shutil, "which", lambda _name: None)
    with pytest.raises(SearchError, match="yt-dlp"):
        search_youtube("anything")


def test_search_limit_is_bounded():
    assert MAX_SEARCH_LIMIT == 25
