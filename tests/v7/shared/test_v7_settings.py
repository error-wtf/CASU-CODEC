"""Strict V7 settings and migration tests."""

import json
from pathlib import Path

import pytest

from v7.shared.settings import (
    PlayerSettings,
    SettingsDecodeError,
    SettingsStore,
    deserialize_settings,
    migrate_v6_settings,
    serialize_settings,
)


def test_defaults_and_deterministic_round_trip() -> None:
    settings = PlayerSettings()
    encoded = serialize_settings(settings)
    assert deserialize_settings(encoded) == settings
    assert serialize_settings(deserialize_settings(encoded)) == encoded


def test_strict_types_reject_v6_truthiness_bug() -> None:
    payload = json.loads(serialize_settings(PlayerSettings()))
    payload["player"]["muted"] = "false"
    with pytest.raises(SettingsDecodeError):
        deserialize_settings(json.dumps(payload))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("volume", -1), ("volume", 201), ("rate", 0.24), ("rate", 4.01),
        ("cache_limit_mib", 65537), ("record_split_minutes", 1441),
        ("visualizer", "fft"), ("repeat_mode", "sometimes"),
        ("record_format", "exe"),
    ],
)
def test_invalid_bounds_and_enums_are_rejected(field: str, value) -> None:
    data = PlayerSettings().to_dict()
    data[field] = value
    with pytest.raises((TypeError, ValueError)):
        PlayerSettings.from_dict(data)


def test_v6_migration_is_pure_and_does_not_coerce_invalid_boolean() -> None:
    source = {
        "version": 1,
        "player": {"volume": 80, "muted": "false", "repeat_mode": "all"},
    }
    original = json.loads(json.dumps(source))
    migrated = migrate_v6_settings(source)
    assert source == original
    assert migrated.volume == 80
    assert migrated.muted is False
    assert migrated.repeat_mode == "all"


def test_future_and_unknown_fields_are_rejected() -> None:
    payload = json.loads(serialize_settings(PlayerSettings()))
    payload["schema_version"] = 99
    with pytest.raises(SettingsDecodeError) as future:
        deserialize_settings(json.dumps(payload))
    assert future.value.code == "UNSUPPORTED_SCHEMA_VERSION"

    payload["schema_version"] = 1
    payload["player"]["secret"] = "must-not-persist"
    with pytest.raises(SettingsDecodeError) as unknown:
        deserialize_settings(json.dumps(payload))
    assert unknown.value.code == "UNKNOWN_PROPERTY"


def test_store_is_atomic_bounded_and_recovers_default(tmp_path: Path) -> None:
    path = tmp_path / "config" / "settings.json"
    store = SettingsStore(path)
    expected = PlayerSettings(volume=42, watched_folders=("/music",))
    store.save(expected)
    assert store.load() == expected
    assert path.stat().st_mode & 0o077 == 0

    path.write_bytes(b"corrupt")
    assert store.load() == PlayerSettings()

    path.write_bytes(b"x" * (1024 * 1024 + 1))
    assert store.load() == PlayerSettings()
