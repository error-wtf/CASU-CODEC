from __future__ import annotations

import ctypes

import numpy as np
import pytest

from casu.libass import LibassError, LibassRenderer
from mpcasu_native_backend import TkCanvasVideoSink


ASS = b"""[Script Info]
ScriptType: v4.00+
PlayResX: 320
PlayResY: 180
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: CASU,DejaVu Sans,28,&H0000FFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:01.00,CASU,,0,0,0,,Styled CASU
"""


def _available():
    try:
        ctypes.CDLL("libass.so.9")
        return True
    except OSError:
        return False


@pytest.mark.skipif(not _available(), reason="libass runtime unavailable")
def test_libass_renders_bounded_transparent_rgba():
    with LibassRenderer(ASS, 320, 180) as renderer:
        active = renderer.render(500)
        inactive = renderer.render(1500)
    assert active.shape == (180, 320, 4) and active.dtype == np.uint8
    assert np.count_nonzero(active[..., 3]) > 0
    assert np.count_nonzero(inactive[..., 3]) == 0
    png = TkCanvasVideoSink._rgba_png(active)
    assert png.startswith(b"\x89PNG\r\n\x1a\n") and b"IHDR" in png and b"IDAT" in png


def test_libass_rejects_unbounded_frame_before_loading_runtime():
    with pytest.raises(LibassError, match="resource limits"):
        LibassRenderer(ASS, 100_000, 100_000)


@pytest.mark.skipif(not _available(), reason="libass runtime unavailable")
def test_libass_rejects_unbounded_embedded_font_name():
    with pytest.raises(LibassError, match="fonts exceed"):
        LibassRenderer(ASS, 320, 180, fonts=(("x" * 256, b"font"),))
