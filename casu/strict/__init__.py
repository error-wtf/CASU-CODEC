"""Source-resolution STRICT primitives for CASU Gate 2.

This package is deliberately independent from the reduced activity-hint
analyzer. It compares canonical decoded planes exactly and requires explicit
source timestamps supplied by the decoder boundary.
"""
from .canonical import CanonicalFrame, canonical_frame
from .model import StrictFrame, StrictTileState
from .state_builder import build_state_map

__all__ = ["CanonicalFrame", "StrictFrame", "StrictTileState", "canonical_frame", "build_state_map"]
