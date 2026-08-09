from casu.library import MediaLibrary, PlaybackPreferences


def test_media_library_scan_resume_favorites_and_playlists(tmp_path):
    first = tmp_path / "a.any"; first.write_bytes(b"a")
    second = tmp_path / "b.casu"; second.write_bytes(b"bb")
    with MediaLibrary(tmp_path / "library.sqlite3") as library:
        scanned = library.scan([first, second])
        assert [item.size_bytes for item in scanned] == [1, 2]
        library.record_progress(first, 12.5, duration_seconds=60)
        library.set_favorite(first, True)
        assert library.get(first).resume_seconds == 12.5
        assert library.items(favorites_only=True)[0].path == first
        library.save_playlist("queue", [second, first])
        assert library.load_playlist("queue") == (second, first)


def test_media_library_completed_item_resets_resume(tmp_path):
    media = tmp_path / "done.bin"; media.write_bytes(b"x")
    with MediaLibrary(tmp_path / "library.sqlite3") as library:
        library.record_progress(media, 58, duration_seconds=60)
        assert library.get(media).resume_seconds == 0


def test_media_library_search_is_bounded_and_escapes_wildcards(tmp_path):
    first = tmp_path / "100%_music.flac"; first.write_bytes(b"a")
    second = tmp_path / "movie.mkv"; second.write_bytes(b"b")
    database = tmp_path / "library.sqlite3"
    with MediaLibrary(database) as library:
        scanned = library.scan([tmp_path])
        assert database not in {item.path for item in scanned}
        assert [item.path for item in library.search("%_")] == [first]
        assert library.search("movie", limit=1)[0].path == second


def test_media_library_playback_preferences_roundtrip_and_clamp(tmp_path):
    media = tmp_path / "movie.mkv"; media.write_bytes(b"movie")
    database = tmp_path / "library.sqlite3"
    with MediaLibrary(database) as library:
        library.set_playback_preferences(media, PlaybackPreferences(
            audio_track=4, video_track=2, subtitle_track=-1,
            audio_delay_ms=9000, subtitle_delay_ms=-9000,
        ))
        value = library.playback_preferences(media)
        assert (value.audio_track, value.video_track, value.subtitle_track) == (4, 2, -1)
        assert value.audio_delay_ms == 5000
        assert value.subtitle_delay_ms == -5000
    # Reopening exercises migrations/columns on an existing database.
    with MediaLibrary(database) as library:
        assert library.playback_preferences(media).audio_track == 4
