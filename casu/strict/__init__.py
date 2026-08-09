"""Source-resolution STRICT primitives for CASU Gate 2.

This package is deliberately independent from the reduced activity-hint
analyzer. It compares canonical decoded planes exactly and requires explicit
source timestamps supplied by the decoder boundary.
"""
from .canonical import CanonicalFrame, PlaneLayout, StrictCanonicalError, canonical_frame
from .model import RationalTime, StrictFrame, StrictTileState
from .state_builder import build_state_map, iter_state_map
from .decoder import StrictDecoderError, iter_source_frames, validate_source_frames

__all__ = ["CanonicalFrame", "PlaneLayout", "RationalTime", "StrictCanonicalError",
           "StrictFrame", "StrictTileState", "StrictDecoderError", "canonical_frame",
           "build_state_map", "iter_state_map", "iter_source_frames", "validate_source_frames"]
