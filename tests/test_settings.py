from casu.settings import PlayerSettings, SettingsStore


def test_settings_roundtrip_is_atomic_and_validated(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.save(PlayerSettings(volume=250, muted=True, rate=9,
                              audio_device="usb", watched_folders=("~/Music",)))
    loaded = store.load()
    assert loaded.volume == 200 and loaded.rate == 4.0 and loaded.muted is True
    assert loaded.audio_device == "usb"
    assert loaded.watched_folders[0].endswith("Music")


def test_invalid_settings_fail_to_defaults(tmp_path):
    path = tmp_path / "settings.json"; path.write_text("not-json", encoding="utf-8")
    assert SettingsStore(path).load() == PlayerSettings()


def test_watched_folders_survive_repeated_save(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    original = PlayerSettings(watched_folders=(str(tmp_path / "Music"),))
    store.save(original)
    loaded = store.load()
    store.save(loaded)
    assert store.load().watched_folders == loaded.watched_folders


def test_settings_read_is_bounded_and_nonfinite_rate_defaults(tmp_path, monkeypatch):
    import casu.settings as settings_module
    path = tmp_path / "settings.json"
    path.write_text('{"version":1,"player":{"rate":NaN}}', encoding="utf-8")
    assert SettingsStore(path).load().rate == 1.0
    path.write_bytes(b"{}" * 9)
    monkeypatch.setattr(settings_module, "MAX_SETTINGS_BYTES", 8)
    assert SettingsStore(path).load() == PlayerSettings()
