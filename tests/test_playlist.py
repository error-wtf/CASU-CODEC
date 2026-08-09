from __future__ import annotations

import pytest

from casu.playlist import PlaylistError, PlaylistModel


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
