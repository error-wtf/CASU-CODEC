"""Small transactional SQLite media library shared by player front ends."""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class LibraryItem:
    path: Path
    size_bytes: int
    modified_ns: int
    favorite: bool
    resume_seconds: float
    duration_seconds: float | None
    metadata: dict


@dataclass(frozen=True)
class PlaybackPreferences:
    audio_track: int | None = None
    video_track: int | None = None
    subtitle_track: int | None = None
    audio_delay_ms: float = 0.0
    subtitle_delay_ms: float = 0.0


class MediaLibrary:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS media (
                path TEXT PRIMARY KEY,
                size_bytes INTEGER NOT NULL,
                modified_ns INTEGER NOT NULL,
                favorite INTEGER NOT NULL DEFAULT 0,
                resume_seconds REAL NOT NULL DEFAULT 0,
                duration_seconds REAL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                audio_track INTEGER,
                video_track INTEGER,
                subtitle_track INTEGER,
                audio_delay_ms REAL NOT NULL DEFAULT 0,
                subtitle_delay_ms REAL NOT NULL DEFAULT 0,
                last_seen_ns INTEGER NOT NULL,
                last_played_ns INTEGER
            );
            CREATE TABLE IF NOT EXISTS playlists (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS playlist_items (
                playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
                position INTEGER NOT NULL,
                media_path TEXT NOT NULL,
                PRIMARY KEY (playlist_id, position)
            );
        """)
        existing = {row[1] for row in self.connection.execute("PRAGMA table_info(media)")}
        migrations = {
            "audio_track": "INTEGER",
            "video_track": "INTEGER",
            "subtitle_track": "INTEGER",
            "audio_delay_ms": "REAL NOT NULL DEFAULT 0",
            "subtitle_delay_ms": "REAL NOT NULL DEFAULT 0",
        }
        for column, declaration in migrations.items():
            if column not in existing:
                self.connection.execute(
                    f"ALTER TABLE media ADD COLUMN {column} {declaration}"
                )
        self.connection.commit()

    def upsert(self, path: str | Path, *, duration_seconds: float | None = None,
               metadata: dict | None = None) -> LibraryItem:
        source = Path(path).expanduser().resolve()
        stat = source.stat()
        now = time.time_ns()
        values = json.dumps(metadata or {}, sort_keys=True, separators=(",", ":"))
        self.connection.execute("""
            INSERT INTO media(path,size_bytes,modified_ns,duration_seconds,metadata_json,last_seen_ns)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(path) DO UPDATE SET
              size_bytes=excluded.size_bytes, modified_ns=excluded.modified_ns,
              duration_seconds=COALESCE(excluded.duration_seconds,media.duration_seconds),
              metadata_json=CASE WHEN excluded.metadata_json='{}' THEN media.metadata_json ELSE excluded.metadata_json END,
              last_seen_ns=excluded.last_seen_ns
        """, (str(source), stat.st_size, stat.st_mtime_ns, duration_seconds, values, now))
        self.connection.commit()
        item = self.get(source)
        assert item is not None
        return item

    def get(self, path: str | Path) -> LibraryItem | None:
        source = str(Path(path).expanduser().resolve())
        row = self.connection.execute("SELECT * FROM media WHERE path=?", (source,)).fetchone()
        return self._item(row) if row else None

    def items(self, *, favorites_only: bool = False) -> tuple[LibraryItem, ...]:
        query = "SELECT * FROM media" + (" WHERE favorite=1" if favorites_only else "") + " ORDER BY path"
        return tuple(self._item(row) for row in self.connection.execute(query))

    def search(self, query: str = "", *, favorites_only: bool = False,
               limit: int = 500) -> tuple[LibraryItem, ...]:
        """Search persistent paths/metadata with a hard result bound."""
        maximum = max(1, min(5000, int(limit)))
        needle = str(query).strip().casefold()
        clauses: list[str] = []
        parameters: list[object] = []
        if favorites_only:
            clauses.append("favorite=1")
        if needle:
            clauses.append("(LOWER(path) LIKE ? ESCAPE '\\' OR LOWER(metadata_json) LIKE ? ESCAPE '\\')")
            escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            parameters.extend((f"%{escaped}%", f"%{escaped}%"))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(maximum)
        rows = self.connection.execute(
            f"SELECT * FROM media{where} ORDER BY COALESCE(last_played_ns,0) DESC,path LIMIT ?",
            parameters,
        )
        return tuple(self._item(row) for row in rows)

    def scan(self, roots: Iterable[str | Path]) -> tuple[LibraryItem, ...]:
        found = []
        for root in roots:
            base = Path(root).expanduser().resolve()
            candidates = (value for value in base.rglob("*") if value.is_file()) if base.is_dir() else (base,)
            for candidate in candidates:
                if candidate == self.path or candidate.name in {
                    f"{self.path.name}-wal", f"{self.path.name}-shm"
                }:
                    continue
                try:
                    found.append(self.upsert(candidate))
                except OSError:
                    continue
        return tuple(found)

    def record_progress(self, path: str | Path, seconds: float,
                        duration_seconds: float | None = None) -> None:
        source = Path(path).expanduser().resolve()
        if self.get(source) is None:
            self.upsert(source, duration_seconds=duration_seconds)
        position = max(0.0, float(seconds))
        if duration_seconds and position >= max(0.0, duration_seconds - 5.0):
            position = 0.0
        self.connection.execute(
            "UPDATE media SET resume_seconds=?,duration_seconds=COALESCE(?,duration_seconds),last_played_ns=? WHERE path=?",
            (position, duration_seconds, time.time_ns(), str(source)))
        self.connection.commit()

    def set_favorite(self, path: str | Path, favorite: bool) -> None:
        source = Path(path).expanduser().resolve()
        if self.get(source) is None:
            self.upsert(source)
        self.connection.execute("UPDATE media SET favorite=? WHERE path=?",
                                (int(bool(favorite)), str(source)))
        self.connection.commit()

    def playback_preferences(self, path: str | Path) -> PlaybackPreferences:
        source = str(Path(path).expanduser().resolve())
        row = self.connection.execute(
            "SELECT audio_track,video_track,subtitle_track,audio_delay_ms,subtitle_delay_ms "
            "FROM media WHERE path=?", (source,)).fetchone()
        if row is None:
            return PlaybackPreferences()
        return PlaybackPreferences(
            int(row["audio_track"]) if row["audio_track"] is not None else None,
            int(row["video_track"]) if row["video_track"] is not None else None,
            int(row["subtitle_track"]) if row["subtitle_track"] is not None else None,
            float(row["audio_delay_ms"]), float(row["subtitle_delay_ms"]),
        )

    def set_playback_preferences(self, path: str | Path,
                                 preferences: PlaybackPreferences) -> None:
        source = Path(path).expanduser().resolve()
        if self.get(source) is None:
            self.upsert(source)
        audio_delay = max(-5000.0, min(5000.0, float(preferences.audio_delay_ms)))
        subtitle_delay = max(-5000.0, min(5000.0, float(preferences.subtitle_delay_ms)))
        self.connection.execute("""
            UPDATE media SET audio_track=?,video_track=?,subtitle_track=?,
              audio_delay_ms=?,subtitle_delay_ms=? WHERE path=?
        """, (preferences.audio_track, preferences.video_track,
              preferences.subtitle_track, audio_delay, subtitle_delay,
              str(source)))
        self.connection.commit()

    def save_playlist(self, name: str, paths: Iterable[str | Path]) -> None:
        title = str(name).strip()
        if not title:
            raise ValueError("playlist name cannot be empty")
        with self.connection:
            self.connection.execute("INSERT INTO playlists(name) VALUES(?) ON CONFLICT(name) DO NOTHING", (title,))
            playlist_id = self.connection.execute("SELECT id FROM playlists WHERE name=?", (title,)).fetchone()[0]
            self.connection.execute("DELETE FROM playlist_items WHERE playlist_id=?", (playlist_id,))
            self.connection.executemany(
                "INSERT INTO playlist_items(playlist_id,position,media_path) VALUES(?,?,?)",
                ((playlist_id, index, str(Path(path).expanduser().resolve()))
                 for index, path in enumerate(paths)))

    def load_playlist(self, name: str) -> tuple[Path, ...]:
        rows = self.connection.execute("""
            SELECT i.media_path FROM playlist_items i
            JOIN playlists p ON p.id=i.playlist_id WHERE p.name=? ORDER BY i.position
        """, (name,))
        return tuple(Path(row[0]) for row in rows)

    @staticmethod
    def _item(row: sqlite3.Row) -> LibraryItem:
        return LibraryItem(Path(row["path"]), int(row["size_bytes"]), int(row["modified_ns"]),
                           bool(row["favorite"]), float(row["resume_seconds"]),
                           float(row["duration_seconds"]) if row["duration_seconds"] is not None else None,
                           json.loads(row["metadata_json"]))

    def close(self) -> None:
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
