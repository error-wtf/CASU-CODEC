"""CASU MP5 — enhanced container with zstd compression and FLAC audio.

MP5 extends CASUNAT2 with:
- zstd compression (better ratio than zlib)
- FLAC-based audio instead of raw PCM
- 10/12/16-bit video plane support
- Optimized seek index with smaller footprint
- Enhanced metadata chunk type
"""
from .format import (ChunkType, CasuLimits, DEFAULT_LIMITS, SeekEntry)
from .reader import (Mp5Error, Mp5Container, read_mp5, extract_attachment,
                     extract_source, verify_mp5)
from .writer import write_mp5
from .converter import convert_to_mp5

__all__ = [
    "ChunkType", "CasuLimits", "DEFAULT_LIMITS", "SeekEntry",
    "Mp5Error", "Mp5Container", "read_mp5", "extract_attachment",
    "extract_source", "verify_mp5",
    "write_mp5", "convert_to_mp5",
]
