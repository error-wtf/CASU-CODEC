from __future__ import annotations

from datetime import datetime, timedelta, timezone

import os
import threading
import time

import pytest

from casu.epg import EpgGuide, Programme, StreamCatalog, StreamChannel

from casu.media import ChapterDescriptor
from mpcasu_backend import PlaybackState
from mpcasu_player import MPCASUPlayer


pytestmark = [pytest.mark.media,
              pytest.mark.skipif(not os.environ.get("DISPLAY"),
                                 reason="Tk display unavailable")]


@pytest.fixture(autouse=True)
def _isolated_player_profile(tmp_path, monkeypatch):
    """GUI tests must never restore or overwrite the user's real session."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


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


def test_playlist_model_keeps_both_real_listboxes_in_sync(tmp_path):
    first = tmp_path / "first.mp4"; first.write_bytes(b"first")
    second = tmp_path / "second.casu"; second.write_bytes(b"second")
    app = MPCASUPlayer()
    try:
        app.add_files([first, second, first])
        assert app.playlist_model.items == (first.resolve(), second.resolve())
        assert app.library.get(0, "end") == (str(first.resolve()), str(second.resolve()))
        assert app.queue.get(0, "end") == ("[MP4] first.mp4", "[CASU] second.casu")
        app.queue.selection_set(0)
        app.move_queue(1)
        assert app.playlist_model.items == (second.resolve(), first.resolve())
        assert app.library.get(0) == str(second.resolve())
        assert app.queue.get(0) == "[CASU] second.casu"
        app.library.selection_clear(0, "end"); app.library.selection_set(0)
        app.remove_selected()
        assert app.playlist_model.items == (first.resolve(),)
        assert app.library.size() == app.queue.size() == 1
    finally:
        app.destroy()


def test_removing_active_file_stops_before_releasing_it(tmp_path, monkeypatch):
    first = tmp_path / "first.mp4"; first.write_bytes(b"first")
    second = tmp_path / "second.mp4"; second.write_bytes(b"second")
    app = MPCASUPlayer()
    stopped = []
    try:
        app.add_files([first, second]); app.current = first.resolve()
        monkeypatch.setattr(app, "stop", lambda: stopped.append(True))
        app.library.selection_set(0)
        app.remove_selected()
        assert stopped == [True]
        assert app.current is None
        assert app.playlist_model.items == (second.resolve(),)
        assert app.library.curselection() == (0,)
    finally:
        app.destroy()


def test_live_tv_epg_dialog_renders_real_loaded_catalog():
    now = datetime.now(timezone.utc)
    app = MPCASUPlayer()
    try:
        app._stream_catalog = StreamCatalog((StreamChannel(
            "https://stream.test/live.m3u8", "News HD", "news", "News"),))
        app._epg_guide = EpgGuide({"news": "News HD"}, (Programme(
            "news", now - timedelta(minutes=10), now + timedelta(minutes=20),
            "Live News", "Headlines", "News"),))
        app.show_epg_dialog(); app.update()
        dialogs = [child for child in app.winfo_children()
                   if child.winfo_class() == "Toplevel"
                   and child.title() == "MPCASU · Live TV & EPG"]
        assert len(dialogs) == 1
        listboxes = []
        def collect(widget):
            for child in widget.winfo_children():
                if child.winfo_class() == "Listbox": listboxes.append(child)
                collect(child)
        collect(dialogs[0])
        assert any("News HD" in box.get(0) for box in listboxes if box.size())
    finally:
        app.destroy()


def test_network_stream_seek_uses_active_controller_without_local_path(monkeypatch):
    app = MPCASUPlayer(); calls = []
    try:
        app.backend = object(); app.current = None
        app._network_source = "https://stream.test/vod.m3u8"
        app.position.set(42)
        monkeypatch.setattr(app.controller, "seek", lambda value: calls.append(("seek", value)))
        monkeypatch.setattr(app.controller, "play", lambda: calls.append(("play", None)))
        app.seek_restart()
        assert calls == [("seek", 42.0), ("play", None)]
    finally:
        app.backend = None; app.destroy()


def test_repeat_all_wraps_real_playlist_and_ab_loop_seeks(tmp_path, monkeypatch):
    first = tmp_path / "one.mp4"; first.write_bytes(b"1")
    second = tmp_path / "two.mp4"; second.write_bytes(b"2")
    app = MPCASUPlayer(); played = []
    class Backend:
        def position(self): return 9.0
    try:
        app.add_files([first, second]); app.current = second.resolve()
        app.library.selection_set(1); app._repeat_mode = "all"
        monkeypatch.setattr(app, "play_selected", lambda: played.append(app.library.curselection()[0]))
        app.play_next(automatic=True)
        assert played == [0]
        app.backend = Backend(); app.cycle_ab_loop()
        assert app._ab_start == 9.0
    finally:
        app.backend = None; app.destroy()


def test_mini_player_hides_product_panels_and_restores_them():
    app = MPCASUPlayer()
    try:
        app.update()
        original = app.geometry()
        original_right = bool(app.right_shell.winfo_ismapped())
        app.toggle_mini_player(); app.update()
        assert app._mini_mode is True
        assert not app.left_shell.winfo_ismapped()
        assert not app.right_shell.winfo_ismapped()
        assert not app.diagnostics.winfo_ismapped()
        assert app.center_shell.winfo_ismapped()
        # Some headless X servers ignore the topmost hint; panel/layout state
        # remains the portable behavior under test.
        app.toggle_mini_player(); app.update()
        assert app._mini_mode is False
        assert app.left_shell.winfo_ismapped()
        assert bool(app.right_shell.winfo_ismapped()) is original_right
        assert app.diagnostics.winfo_ismapped()
        assert app.geometry() == original
    finally:
        app.destroy()


def test_backend_event_never_enters_tcl_from_worker_thread(monkeypatch):
    app = MPCASUPlayer()
    try:
        monkeypatch.setattr(app, "after", lambda *_args, **_kwargs:
                            (_ for _ in ()).throw(AssertionError("worker entered Tcl")))
        worker = threading.Thread(target=app._backend_event,
                                  args=(PlaybackState.PAUSED,))
        worker.start(); worker.join(timeout=1)
        assert not worker.is_alive()
        assert app._paused is False
        app._drain_backend_events()
        assert app._paused is True
    finally:
        app.destroy()


def test_stop_detaches_before_a_blocking_third_party_backend_close():
    entered = threading.Event(); release = threading.Event()
    class BlockingBackend:
        on_event = object()
        def close(self):
            entered.set(); release.wait(2)
    app = MPCASUPlayer(); backend = BlockingBackend()
    try:
        app.backend = backend; app.controller.attach(backend, "blocking")
        started = time.monotonic(); app.stop(); elapsed = time.monotonic() - started
        assert elapsed < .2
        assert app.backend is None and app.controller.backend is None
        assert entered.wait(1)
    finally:
        release.set(); app.destroy()
