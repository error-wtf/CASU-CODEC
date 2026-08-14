from __future__ import annotations

import pytest

from casu.playlist import (PlaylistError, PlaylistModel, load_playlist_file,
                           save_playlist_file)


def test_playlist_model_is_single_ordered_duplicate_free_source(tmp_path):
    first = tmp_path / "first.mp4"; first.write_bytes(b"1")
    second = tmp_path / "second.casu"; second.write_bytes(b"2")
    model = PlaylistModel()
    assert model.add((first, second, first), existing_only=True) == 2
    assert model.items == (first.resolve(), second.resolve())
    assert model.index_of(second) == 1
    assert model.index_of(tmp_path / "missing.mp4") is None
    assert model.move(0, 1) == 1
    assert model.items == (second.resolve(), first.resolve())
    model.remove((1,))
    assert model.items == (second.resolve(),)
    model.clear()
    assert model.items == ()


def test_playlist_payload_roundtrip_and_validation(tmp_path):
    media = tmp_path / "track.mp3"; media.write_bytes(b"audio")
    original = PlaylistModel((media,))
    restored = PlaylistModel.from_payload(original.to_payload(), existing_only=True)
    assert restored.items == original.items
    with pytest.raises(PlaylistError, match="unsupported"):
        PlaylistModel.from_payload({"version": 2, "items": []})
    with pytest.raises(PlaylistError, match="paths"):
        PlaylistModel.from_payload({"version": 1, "items": [1]})
    with pytest.raises(PlaylistError, match="invalid"):
        PlaylistModel(("bad\0path",))


def test_playlist_file_roundtrip_is_atomic_and_rejects_invalid_utf8(tmp_path):
    media = tmp_path / "track.mp3"; media.write_bytes(b"audio")
    target = tmp_path / "playlist.json"
    save_playlist_file(target, PlaylistModel((media,)))
    assert load_playlist_file(target, existing_only=True).items == (media.resolve(),)
    assert not list(tmp_path.glob(".playlist.json.*"))
    target.write_bytes(b"\xff\xfe")
    with pytest.raises(PlaylistError, match="UTF-8 JSON"):
        load_playlist_file(target)


def test_playlist_file_read_is_bounded(tmp_path, monkeypatch):
    import casu.playlist as playlist
    target = tmp_path / "large.json"; target.write_bytes(b"{}" * 9)
    monkeypatch.setattr(playlist, "MAX_PLAYLIST_FILE_BYTES", 8)
    with pytest.raises(PlaylistError, match="safety limit"):
        load_playlist_file(target)
