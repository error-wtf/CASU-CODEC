from __future__ import annotations

import os

import pytest

from casu.media import ChapterDescriptor
from mpcasu_backend import PlaybackState
from mpcasu_player import MPCASUPlayer


pytestmark = [pytest.mark.media,
              pytest.mark.skipif(not os.environ.get("DISPLAY"),
                                 reason="Tk display unavailable")]


class _ChapterBackend:
    def __init__(self):
        self.selected: list[int] = []

    def chapter_descriptors(self):
        return (ChapterDescriptor(0, 0.0, "Intro", 50.0),
                ChapterDescriptor(1, 50.0, "Middle", 100.0))

    def chapter(self):
        return self.selected[-1] if self.selected else 0

    def set_chapter(self, identifier):
        self.selected.append(int(identifier))

    def position(self):
        return 50.0

    def state(self):
        return PlaybackState.PAUSED


def test_chapter_timeline_draws_and_clicks_real_markers():
    app = MPCASUPlayer()
    try:
        app.backend = _ChapterBackend()
        app.duration = 100.0
        app.update()
        app._draw_chapter_markers()
        app.update()
        markers = app.chapter_timeline.find_withtag("chapter-marker")
        assert len(markers) == 2
        box = app.chapter_timeline.bbox(markers[1])
        assert box is not None
        app.chapter_timeline.event_generate(
            "<Button-1>", x=(box[0] + box[2]) // 2, y=(box[1] + box[3]) // 2)
        app.update()
        assert app.backend.selected == [1]
        assert app.position.get() == 50.0
    finally:
        app.backend = None
        app.destroy()
