"""Validated, atomic MPCASU settings."""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class PlayerSettings:
    volume: int = 100
    muted: bool = False
    rate: float = 1.0
    audio_device: str | None = None
    watched_folders: tuple[str, ...] = ()

    def validated(self) -> "PlayerSettings":
        return PlayerSettings(max(0, min(200, int(self.volume))), bool(self.muted),
                              max(0.25, min(4.0, float(self.rate))),
                              str(self.audio_device) if self.audio_device else None,
                              tuple(str(Path(value).expanduser()) for value in self.watched_folders))


class SettingsStore:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()

    def load(self) -> PlayerSettings:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if value.get("version") != 1:
                return PlayerSettings()
            settings = value.get("player", {})
            return PlayerSettings(
                settings.get("volume", 100), settings.get("muted", False),
                settings.get("rate", 1.0), settings.get("audio_device"),
                tuple(settings.get("watched_folders", ())),
            ).validated()
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return PlayerSettings()

    def save(self, settings: PlayerSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"version": 1, "player": asdict(settings.validated())},
                             indent=2, ensure_ascii=False) + "\n"
        fd, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload); handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
