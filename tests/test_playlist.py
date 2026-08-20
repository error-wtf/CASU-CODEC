from __future__ import annotations

import pytest

from casu.playlist import (PlaylistError, PlaylistModel, detect_playlist_format,
                           load_playlist_file, playlist_names,
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


def test_plain_m3u_without_header_is_detected(tmp_path):
    media = tmp_path / "track.mp3"; media.write_bytes(b"audio")
    source = tmp_path / "plain.m3u"
    source.write_text(f"{media.name}\n{tmp_path / 'other.mp3'}\n", encoding="utf-8")
    assert detect_playlist_format(source) == "m3u"
    loaded = load_playlist_file(source)
    assert media.resolve() in loaded.items
    assert len(loaded) == 2


def test_m3u_relative_and_url_encoded_paths_resolve(tmp_path):
    sub = tmp_path / "my folder"; sub.mkdir()
    media = sub / "track a.mp3"; media.write_bytes(b"audio")
    source = tmp_path / "list.m3u"
    source.write_text("#EXTM3U\n#EXTINF:42,The Title\nmy%20folder/track%20a.mp3\n", encoding="utf-8")
    loaded = load_playlist_file(source)
    assert loaded.items == (media.resolve(),)
    names = playlist_names(source)
    assert names[str(media.resolve())] == "The Title"


def test_pls_relative_paths_and_titles(tmp_path):
    media = tmp_path / "song.flac"; media.write_bytes(b"audio")
    source = tmp_path / "list.pls"
    source.write_text("[playlist]\nNumberOfEntries=1\nFile1=song.flac\nTitle1=My Song\n"
                      "Length1=-1\nVersion=2\n", encoding="utf-8")
    assert detect_playlist_format(source) == "pls"
    loaded = load_playlist_file(source)
    assert loaded.items == (media.resolve(),)
    assert playlist_names(source)[str(media.resolve())] == "My Song"


def test_xspf_playlist(tmp_path):
    media = tmp_path / "clip.mp4"; media.write_bytes(b"video")
    source = tmp_path / "list.xspf"
    source.write_text(
        '<?xml version="1.0"?>\n'
        '<playlist version="1" xmlns="http://xspf.org/ns/0/">\n'
        "  <trackList>\n"
        "    <track><location>clip.mp4</location><title>Clip One</title></track>\n"
        '    <track><location>http://example.com/radio</location><title>Radio</title></track>\n'
        "  </trackList>\n"
        "</playlist>\n", encoding="utf-8")
    assert detect_playlist_format(source) == "xspf"
    loaded = load_playlist_file(source)
    assert loaded.items == (media.resolve(), "http://example.com/radio")
    names = playlist_names(source)
    assert names[str(media.resolve())] == "Clip One"
    assert names["http://example.com/radio"] == "Radio"


def test_wpl_playlist(tmp_path):
    media = tmp_path / "song.wma"; media.write_bytes(b"audio")
    source = tmp_path / "list.wpl"
    source.write_text(
        '<?wpl version="1.0"?>\n<smil><head></head><body><seq>\n'
        '<media src="song.wma"/>\n'
        '<media src="http://example.com/stream"/>\n'
        "</seq></body></smil>\n", encoding="utf-8")
    assert detect_playlist_format(source) == "wpl"
    assert load_playlist_file(source).items == (media.resolve(), "http://example.com/stream")


def test_asx_playlist_case_insensitive(tmp_path):
    media = tmp_path / "show.wmv"; media.write_bytes(b"video")
    source = tmp_path / "list.asx"
    source.write_text(
        '<ASX version="3.0">\n'
        '<ENTRY><TITLE>Cool Show</TITLE><REF HREF="show.wmv"/></ENTRY>\n'
        '<ENTRY><REF HREF="http://example.com/live"/></ENTRY>\n'
        "</ASX>\n", encoding="utf-8")
    assert detect_playlist_format(source) == "asx"
    loaded = load_playlist_file(source)
    assert loaded.items == (media.resolve(), "http://example.com/live")
    assert playlist_names(source).get(str(media.resolve())) == "Cool Show"


def test_jspf_playlist(tmp_path):
    media = tmp_path / "track.ogg"; media.write_bytes(b"audio")
    source = tmp_path / "list.jspf"
    source.write_text(
        '{"playlist":{"title":"Mix","track":['
        '{"location":"track.ogg","title":"Ogg Track"},'
        '{"location":"http://example.com/radio"}]}}', encoding="utf-8")
    assert detect_playlist_format(source) == "jspf"
    loaded = load_playlist_file(source)
    assert loaded.items == (media.resolve(), "http://example.com/radio")
    assert playlist_names(source)[str(media.resolve())] == "Ogg Track"


def test_rmp_ram_playlist(tmp_path):
    media = tmp_path / "show.rm"; media.write_bytes(b"audio")
    ram = tmp_path / "list.ram"
    ram.write_text("show.rm\nhttp://example.com/radio.ra\n", encoding="utf-8")
    assert detect_playlist_format(ram) == "rmp"
    assert load_playlist_file(ram).items == (media.resolve(), "http://example.com/radio.ra")
    rmp = tmp_path / "list.rmp"
    rmp.write_text(
        '<Smil><Seq><Entry><Ref Href="show.rm"/></Entry></Seq></Smil>\n',
        encoding="utf-8")
    assert detect_playlist_format(rmp) == "rmp"
    assert load_playlist_file(rmp).items == (media.resolve(),)


def test_file_url_and_xspf_save_roundtrip(tmp_path):
    media = tmp_path / "file one.mp3"; media.write_bytes(b"audio")
    source = tmp_path / "urls.m3u"
    source.write_text(f"file://{media}\n", encoding="utf-8")
    loaded = load_playlist_file(source)
    assert loaded.items == (media.resolve(),)
    target = tmp_path / "saved.xspf"
    save_playlist_file(target, loaded)
    assert load_playlist_file(target).items == (media.resolve(),)


def test_unknown_playlist_format_raises(tmp_path):
    source = tmp_path / "list.txt"
    source.write_text("   \n\t\n  \n", encoding="utf-8")
    with pytest.raises(PlaylistError, match="unknown playlist format"):
        load_playlist_file(source)


def test_malformed_xml_playlist_raises(tmp_path):
    source = tmp_path / "list.xspf"
    source.write_text("<playlist><trackList><track><location></trackList>", encoding="utf-8")
    with pytest.raises(PlaylistError, match="malformed"):
        load_playlist_file(source)


def test_merge_into_existing_playlist_appends_and_deduplicates(tmp_path):
    """Merge (append) new media/URLs into an existing playlist without dupes."""
    a = tmp_path / "a.mp3"; a.write_bytes(b"a")
    b = tmp_path / "b.mp3"; b.write_bytes(b"b")
    playlist = tmp_path / "mylist.m3u"
    save_playlist_file(playlist, PlaylistModel((a,)))

    # Merge b (new) and a (already present -> skipped) into the playlist.
    model = load_playlist_file(playlist)
    before = len(model.items)
    model.add((b, a))
    assert len(model.items) == before + 1  # only b added, a deduplicated
    save_playlist_file(playlist, model)

    restored = load_playlist_file(playlist)
    assert restored.items == (a.resolve(), b.resolve())


def test_merge_creates_new_playlist_from_selection(tmp_path):
    """Creating a fresh playlist from selected media/URLs persists them."""
    media = tmp_path / "track.mp4"; media.write_bytes(b"video")
    url = "https://example.com/live/stream.m3u8"
    model = PlaylistModel()
    model.add((media, url))
    target = tmp_path / "newlist.m3u"
    save_playlist_file(target, model)
    restored = load_playlist_file(target)
    assert str(restored.items[0]) == str(media.resolve())
    assert str(restored.items[1]) == url


def test_merge_mixed_playlist_and_urls_keeps_order(tmp_path):
    """A mixed queue (playlist entries + standalone URL) persists in order."""
    a = tmp_path / "a.flac"; a.write_bytes(b"flac")
    url1 = "https://example.com/one.m3u8"
    url2 = "https://example.com/two.m3u8"
    model = PlaylistModel()
    model.add((a, url1, url2))
    target = tmp_path / "mixed.m3u"
    save_playlist_file(target, model)
    restored = load_playlist_file(target)
    items = [str(i) for i in restored.items]
    assert items[0] == str(a.resolve())
    assert items[1] == url1
    assert items[2] == url2


def test_merge_handles_missing_files_and_bad_urls_without_crash(tmp_path):
    """Fehlerbehandlung: kaputte/leere Playlists und fehlende Dateien dürfen
    beim Merge/Playlist-Play keinen Absturz verursachen (fehlertolerant)."""
    import casu.playlist as playlist

    # Leere Playlist: load gibt leeres Model, kein Fehler.
    empty = tmp_path / "empty.m3u"
    empty.write_text("#EXTM3U\n", encoding="utf-8")
    assert len(load_playlist_file(empty).items) == 0

    # Kaputte Playlist (ungültiges XML) -> PlaylistError (kein Crash).
    bad = tmp_path / "bad.xspf"
    bad.write_text("<playlist><trackList>", encoding="utf-8")
    with pytest.raises(PlaylistError):
        load_playlist_file(bad)

    # Fehlende Datei im PlaylistModel -> existing_only überspringt sie.
    model = PlaylistModel()
    model.add((tmp_path / "missing.mp4",), existing_only=True)
    assert model.items == ()


def test_playlist_play_queue_roundtrip_dedups_and_orders(tmp_path):
    """Kernlogik von _play_playlist_full: Playlist in Queue + dedupliziert +
    Reihenfolge erhalten, sodass play_next durchspielt."""
    a = tmp_path / "a.mp3"; a.write_bytes(b"a")
    b = tmp_path / "b.mp3"; b.write_bytes(b"b")
    playlist = tmp_path / "tracks.m3u"
    save_playlist_file(playlist, PlaylistModel((a, b)))

    # Simuliere _play_playlist_full: alle Einträge in die Queue.
    model = PlaylistModel()
    loaded = load_playlist_file(playlist)
    model.add(loaded.items)
    assert len(model.items) == 2
    assert model.items == (a.resolve(), b.resolve())
    # Erneut adden (idempotent, keine Duplikate).
    model.add(loaded.items)
    assert len(model.items) == 2
    # Reihenfolge erhalten -> index_of(a)==0, index_of(b)==1 (play_next von a -> b).
    assert model.index_of(a) == 0
    assert model.index_of(b) == 1


def test_replace_with_resolves_playlist_group_in_place(tmp_path):
    """Kernoperation der Playlist-Reparatur: die .m3u-Gruppen-Zeile wird an
    Ort und Stelle durch ihre Einträge ersetzt — kanonische Mischreihenfolge
    (Playlist A: A1, A2 + Datei X + Playlist B: B1, B2 -> A1, A2, X, B1, B2)."""
    a1 = tmp_path / "a1.mp3"; a1.write_bytes(b"a")
    a2 = tmp_path / "a2.mp3"; a2.write_bytes(b"a")
    x = tmp_path / "x.mp4"; x.write_bytes(b"x")
    b1 = tmp_path / "b1.mp3"; b1.write_bytes(b"b")
    b2 = tmp_path / "b2.mp3"; b2.write_bytes(b"b")
    plA = tmp_path / "A.m3u"
    plB = tmp_path / "B.m3u"
    save_playlist_file(plA, PlaylistModel((a1, a2)))
    save_playlist_file(plB, PlaylistModel((b1, b2)))

    queue = PlaylistModel((plA, x, plB))
    inserted = queue.replace_with(queue.index_of(plA), load_playlist_file(plA).items)
    assert inserted == [a1.resolve(), a2.resolve()]
    assert queue.items == (a1.resolve(), a2.resolve(), x.resolve(), plB.resolve())
    inserted = queue.replace_with(queue.index_of(plB), load_playlist_file(plB).items)
    assert inserted == [b1.resolve(), b2.resolve()]
    assert queue.items == (a1.resolve(), a2.resolve(), x.resolve(),
                           b1.resolve(), b2.resolve())

    # Dedup: bereits gequeuete Einträge werden nicht dupliziert.
    queue2 = PlaylistModel((a1, plA))
    inserted = queue2.replace_with(queue2.index_of(plA), load_playlist_file(plA).items)
    assert inserted == [a2.resolve()]
    assert queue2.items == (a1.resolve(), a2.resolve())

    # Rekursion: eine Playlist kann sich nie selbst enthalten.
    queue3 = PlaylistModel((plA,))
    inserted = queue3.replace_with(0, [a1, plA])
    assert inserted == [a1.resolve()]
    assert queue3.items == (a1.resolve(),)

    with pytest.raises(PlaylistError, match="out of range"):
        queue.replace_with(99, [a1])
