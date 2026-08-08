"""CASUNAT2 segmented container primitives.

This is intentionally independent from the CASUNAT1 compatibility envelope.
It stores typed chunks and an on-disk byte-offset index; it never references a
source pathname for payload reconstruction.
"""
from .format import ChunkType, NativeChunk, SeekEntry
from .reader import NativeV2Container, NativeV2Error, read_native_v2
from .writer import write_native_v2
from .video import TileStateCache, VideoPayloadError, decode_key_state, encode_key_state, encode_tile_update
from .audio import AudioBlock, AudioPayloadError, decode_audio_block, encode_audio_block
from .text import (SubtitlePacket, TextPayloadError, decode_chapter_table,
                   decode_subtitle_packet, encode_chapter_table,
                   encode_subtitle_packet)

__all__ = ["ChunkType", "NativeChunk", "SeekEntry", "NativeV2Container",
           "NativeV2Error", "read_native_v2", "write_native_v2"]
__all__ += ["TileStateCache", "VideoPayloadError", "decode_key_state", "encode_key_state",
            "encode_tile_update", "AudioBlock", "AudioPayloadError", "decode_audio_block",
            "encode_audio_block"]
__all__ += ["SubtitlePacket", "TextPayloadError", "decode_chapter_table",
            "decode_subtitle_packet", "encode_chapter_table", "encode_subtitle_packet"]
