"""CASUNAT2 segmented container primitives.

This is intentionally independent from the CASUNAT1 compatibility envelope.
It stores typed chunks and an on-disk byte-offset index; it never references a
source pathname for payload reconstruction.
"""
from .format import ChunkType, NativeChunk, SeekEntry
from .reader import NativeV2Container, NativeV2Error, read_native_v2
from .writer import write_native_v2

__all__ = ["ChunkType", "NativeChunk", "SeekEntry", "NativeV2Container",
           "NativeV2Error", "read_native_v2", "write_native_v2"]
