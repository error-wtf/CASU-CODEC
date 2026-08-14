"""CASUNAT2 segmented container primitives.

This is intentionally independent from the CASUNAT1 compatibility envelope.
It stores typed chunks and an on-disk byte-offset index; it never references a
source pathname for payload reconstruction.
"""
from .format import (DEFAULT_LIMITS, CasuLimits, ChunkType, NativeChunk,
                     SeekEntry)
from .reader import (NativeV2Container, NativeV2Error, NativeV2Recovery,
                     ReconstructionPlan, read_native_v2, recover_native_v2,
                     repair_native_v2)
from .writer import write_native_v2
from .video import (TileStateCache, VideoPayloadError, decode_format_change,
                    decode_key_state, encode_format_change, encode_key_state,
                    encode_tile_update)
from .audio import AudioBlock, AudioPayloadError, decode_audio_block, encode_audio_block
from .text import (SubtitlePacket, TextPayloadError, decode_chapter_table,
                   decode_subtitle_packet, encode_chapter_table,
                   encode_subtitle_packet)
from .converter import NativeConversionError, convert_media_to_native_v2
from .attachment import (Attachment, AttachmentPayloadError, decode_attachment,
                         encode_attachment)
from .bitmap import (BitmapSubtitle, BitmapSubtitleError,
                     decode_bitmap_subtitle, encode_bitmap_subtitle)

__all__ = ["ChunkType", "NativeChunk", "SeekEntry", "NativeV2Container", "ReconstructionPlan",
           "NativeV2Error", "NativeV2Recovery", "read_native_v2", "recover_native_v2",
           "repair_native_v2",
           "write_native_v2"]
__all__ += ["CasuLimits", "DEFAULT_LIMITS"]
__all__ += ["TileStateCache", "VideoPayloadError", "decode_key_state", "encode_key_state",
            "encode_tile_update", "AudioBlock", "AudioPayloadError", "decode_audio_block",
            "encode_audio_block"]
__all__ += ["decode_format_change", "encode_format_change"]
__all__ += ["SubtitlePacket", "TextPayloadError", "decode_chapter_table",
            "decode_subtitle_packet", "encode_chapter_table", "encode_subtitle_packet"]
__all__ += ["NativeConversionError", "convert_media_to_native_v2"]
__all__ += ["Attachment", "AttachmentPayloadError", "decode_attachment",
            "encode_attachment"]
__all__ += ["BitmapSubtitle", "BitmapSubtitleError", "decode_bitmap_subtitle",
            "encode_bitmap_subtitle"]
