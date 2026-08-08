from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class ChunkType(IntEnum):
    STREAM_CONFIG = 1
    VIDEO_KEY_STATE = 16
    VIDEO_TILE_UPDATE = 17
    VIDEO_FORMAT_CHANGE = 18
    AUDIO_BLOCK = 32
    SUBTITLE_PACKET = 48
    CHAPTER_TABLE = 64
    ATTACHMENT = 65
    RECOVERY_POINT = 224
    SEEK_INDEX = 240
    INTEGRITY_TABLE = 241
    END = 255


@dataclass(frozen=True)
class NativeChunk:
    chunk_type: ChunkType
    stream_id: int
    pts: int
    payload: bytes
    flags: int = 0
    uncompressed_length: int | None = None


@dataclass(frozen=True)
class SeekEntry:
    stream_id: int
    target_pts: int
    key_state_pts: int
    key_state_offset: int
    first_update_offset: int

