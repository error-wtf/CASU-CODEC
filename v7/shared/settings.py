"""Versioned, strict and atomically published V7 player settings."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any

from v7.shared.limits import SETTINGS_DOCUMENT_BYTES, SETTING_TEXT_BYTES, WATCHED_FOLDERS


MAX_SETTINGS_BYTES = SETTINGS_DOCUMENT_BYTES.maximum
MAX_WATCHED_FOLDERS = WATCHED_FOLDERS.maximum
MAX_SETTING_TEXT_BYTES = SETTING_TEXT_BYTES.maximum
CURRENT_SETTINGS_SCHEMA_VERSION = 1


class SettingsDecodeError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class PlayerSettings:
    volume: int = 100
    muted: bool = False
    rate: float = 1.0
    audio_device: str | None = None
    watched_folders: tuple[str, ...] = ()
    ytdlp_consent: bool = False
    visualizer: str = "waveform"
    resume_playback: bool = True
    cache_limit_mib: int = 512
    recordings_dir: str = ""
    record_split_minutes: int = 0
    record_format: str = "mkv"
    shuffle: bool = False
    repeat_mode: str = "off"

    def __post_init__(self) -> None:
        _integer(self.volume, "volume", 0, 200)
        _boolean(self.muted, "muted")
        if isinstance(self.rate, bool) or not isinstance(self.rate, (int, float)):
            raise TypeError("rate must be numeric")
        if not math.isfinite(float(self.rate)) or not 0.25 <= float(self.rate) <= 4.0:
            raise ValueError("rate must be finite and within 0.25..4.0")
        _optional_text(self.audio_device, "audio_device")
        if not isinstance(self.watched_folders, tuple) or len(self.watched_folders) > MAX_WATCHED_FOLDERS:
            raise ValueError("watched_folders must be a tuple with at most 100 entries")
        for value in self.watched_folders:
            _text(value, "watched_folder")
        _boolean(self.ytdlp_consent, "ytdlp_consent")
        if self.visualizer not in {"waveform", "off"}:
            raise ValueError("invalid visualizer")
        _boolean(self.resume_playback, "resume_playback")
        _integer(self.cache_limit_mib, "cache_limit_mib", 0, 65536)
        _text(self.recordings_dir, "recordings_dir")
        _integer(self.record_split_minutes, "record_split_minutes", 0, 1440)
        if self.record_format not in {"mkv", "mp4", "ts", "webm", "ogg", "mp3", "flac", "wav"}:
            raise ValueError("invalid record_format")
        _boolean(self.shuffle, "shuffle")
        if self.repeat_mode not in {"off", "all", "one"}:
            raise ValueError("invalid repeat_mode")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["watched_folders"] = list(self.watched_folders)
        return value

    @classmethod
    def from_dict(cls, value: object) -> PlayerSettings:
        if not isinstance(value, dict):
            raise TypeError("player settings must be an object")
        names = {item.name for item in fields(cls)}
        unknown = set(value) - names
        if unknown:
            raise SettingsDecodeError("UNKNOWN_PROPERTY", repr(sorted(unknown)))
        normalized = dict(value)
        if "watched_folders" in normalized:
            watched = normalized["watched_folders"]
            if not isinstance(watched, list):
                raise TypeError("watched_folders must be an array")
            normalized["watched_folders"] = tuple(watched)
        return cls(**normalized)


def serialize_settings(value: PlayerSettings) -> bytes:
    if not isinstance(value, PlayerSettings):
        raise TypeError("value must be PlayerSettings")
    return json.dumps(
        {"schema_version": CURRENT_SETTINGS_SCHEMA_VERSION, "player": value.to_dict()},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def deserialize_settings(raw: bytes | str) -> PlayerSettings:
    try:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    except UnicodeDecodeError as error:
        raise SettingsDecodeError("INVALID_UTF8", str(error)) from error
    if not isinstance(text, str):
        raise SettingsDecodeError("INVALID_INPUT_TYPE", "input must be bytes or str")
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, RecursionError) as error:
        raise SettingsDecodeError("MALFORMED_JSON", str(error)) from error
    if not isinstance(value, dict):
        raise SettingsDecodeError("INVALID_SHAPE", "settings root must be an object")
    if set(value) - {"schema_version", "player"}:
        raise SettingsDecodeError("UNKNOWN_PROPERTY", "unknown root property")
    if set(value) != {"schema_version", "player"}:
        raise SettingsDecodeError("MISSING_PROPERTY", "incomplete settings envelope")
    if type(value["schema_version"]) is not int or value["schema_version"] != CURRENT_SETTINGS_SCHEMA_VERSION:
        raise SettingsDecodeError("UNSUPPORTED_SCHEMA_VERSION", repr(value["schema_version"]))
    try:
        return PlayerSettings.from_dict(value["player"])
    except SettingsDecodeError:
        raise
    except (TypeError, ValueError) as error:
        raise SettingsDecodeError("INVALID_VALUE", str(error)) from error


def migrate_v6_settings(value: object) -> PlayerSettings:
    """Pure best-effort migration from the documented V6 version-1 envelope."""
    if not isinstance(value, dict) or value.get("version") != 1:
        return PlayerSettings()
    player = value.get("player")
    if not isinstance(player, dict):
        return PlayerSettings()
    defaults = PlayerSettings().to_dict()
    for name in defaults:
        candidate = player.get(name, defaults[name])
        if isinstance(defaults[name], bool) and type(candidate) is not bool:
            continue
        defaults[name] = candidate
    try:
        return PlayerSettings.from_dict(defaults)
    except (SettingsDecodeError, TypeError, ValueError):
        return PlayerSettings()


class SettingsStore:
    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)

    def load(self) -> PlayerSettings:
        try:
            with self.path.open("rb") as stream:
                data = stream.read(MAX_SETTINGS_BYTES + 1)
            if len(data) > MAX_SETTINGS_BYTES:
                return PlayerSettings()
            return deserialize_settings(data)
        except (OSError, SettingsDecodeError):
            return PlayerSettings()

    def save(self, settings: PlayerSettings) -> None:
        data = serialize_settings(settings)
        if len(data) > MAX_SETTINGS_BYTES:
            raise ValueError("settings document exceeds 1 MiB")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent)
        temporary = Path(name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                descriptor = -1
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            temporary = None
            if os.name != "nt":
                directory = os.open(self.path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if temporary is not None:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass


def _boolean(value: object, name: str) -> None:
    if type(value) is not bool:
        raise TypeError(f"{name} must be boolean")


def _integer(value: object, name: str, minimum: int, maximum: int) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be within {minimum}..{maximum}")


def _text(value: object, name: str) -> None:
    if not isinstance(value, str) or "\0" in value or len(value.encode("utf-8")) > MAX_SETTING_TEXT_BYTES:
        raise ValueError(f"invalid {name}")


def _optional_text(value: object, name: str) -> None:
    if value is not None:
        _text(value, name)
