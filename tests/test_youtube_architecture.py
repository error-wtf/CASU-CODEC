"""Architecture tests: YouTube must use the normal libVLC pipeline.

No second player, no QWebEngineView playback, no webbrowser.open() fallback,
no caption/badge overlays over the native VideoSurface for video.
"""

import os
import time
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu"
)

import pytest
from PySide6.QtWidgets import QApplication

from mpcasu_qt import main_window as mw_module
from mpcasu_qt.main_window import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def mw(app):
    window = MainWindow()
    yield window
    window.close()


class _StubBackend:
    """Minimal LibVLCBackend stand-in so play_selected never touches libVLC."""

    def __init__(self, handle, *, runtime_options=()):
        assert runtime_options == ()
        self.handle = handle
        self.on_event = None

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._noop

    @staticmethod
    def _noop(*_args, **_kwargs):
        return 0.0

    def open(self, source):
        pass

    def open_source(self, source):
        pass

    def position(self):
        return 0.0

    def duration(self):
        return 0.0

    def chapter_descriptors(self):
        return []

    def chapter(self):
        return -1

    def capabilities(self):
        return {"version": "test-stub"}


def _wait_for(app, predicate, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    app.processEvents()
    return predicate()


def test_youtube_resolve_feeds_libvlc_external_source(app, mw, monkeypatch):
    """YouTube resolution must end up in the normal external-source pipeline.

    The shared web-casu resolver (resolve_media_location) produces the direct
    URL; the proxy only transports it; libVLC plays the loopback media URL.
    """
    calls = []
    monkeypatch.setattr(
        mw, "_open_external_source",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        mw_module, "resolve_media_location",
        lambda url, **_kw: f"https://rr1.googlevideo.com/videoplayback?src={url}",
    )
    starts = []

    def fake_start(media_url, *, refresh=None):
        starts.append((media_url, refresh))
        return "http://127.0.0.1:9999/SECRET/media"

    monkeypatch.setattr(mw._yt_stream, "start", fake_start)
    mw._play_youtube("https://www.youtube.com/watch?v=xyz123", label="Titel")
    assert _wait_for(app, lambda: bool(calls))
    args, kwargs = calls[0]
    assert args[0] == "http://127.0.0.1:9999/SECRET/media"
    assert kwargs.get("youtube") is True
    assert kwargs.get("preserve_proxy") is True
    assert kwargs.get("display_label") == "Titel"
    # The proxy received the RESOLVED media URL from the shared resolver,
    # never the YouTube page URL; refresh re-runs that same resolver.
    page_url = "https://www.youtube.com/watch?v=xyz123"
    assert starts[0][0] == f"https://rr1.googlevideo.com/videoplayback?src={page_url}"
    assert starts[0][1]() == f"https://rr1.googlevideo.com/videoplayback?src={page_url}"


def test_proxy_lifecycle_stop_then_start_never_after(app, mw, monkeypatch):
    """The transport for a new YouTube source is never killed after it starts.

    Regression test for the 'Playback error detected' bug: playback cleanup
    (stop -> _stop_yt_transport -> proxy.stop) must run BEFORE the new proxy
    is created, otherwise libVLC opens a dead loopback port.
    """
    events = []
    real_stop = mw._yt_stream.stop
    monkeypatch.setattr(
        mw._yt_stream, "stop",
        lambda *a, **k: (events.append("yt-stop"), real_stop(*a, **k))[1],
    )
    monkeypatch.setattr(
        mw._yt_stream, "start",
        lambda media_url, *, refresh=None: (
            events.append("yt-start"), "http://127.0.0.1:9999/SECRET/media")[1],
    )
    monkeypatch.setattr(
        mw, "_open_external_source",
        lambda *a, **k: events.append("open"),
    )
    monkeypatch.setattr(
        mw_module, "resolve_media_location",
        lambda url, **_kw: "https://rr1.googlevideo.com/videoplayback",
    )
    mw._play_youtube("https://www.youtube.com/watch?v=xyz123", label="Titel")
    assert _wait_for(app, lambda: "open" in events)
    # ordering must be: stop ... start ... open  (never stop after start)
    assert events.index("yt-stop") < events.index("yt-start")
    assert events.index("yt-start") < events.index("open")


def test_stop_shuts_transport_down_before_the_player_session(mw, monkeypatch):
    """Verified v5.0.0 contract: stop() tears the loopback transport down
    FIRST. Killing the server while libVLC is still connected unblocks any
    pending input reads, so the synchronous player teardown can never wait
    on a live socket (the consumer-first order shipped in a later build and
    regressed against the verified release).
    """
    events = []
    mw.backend = object()
    monkeypatch.setattr(mw, "_persist_media_preferences", lambda: None)
    monkeypatch.setattr(mw.controller, "stop", lambda: events.append("player-stop"))
    monkeypatch.setattr(mw.controller, "close", lambda: events.append("player-close"))
    monkeypatch.setattr(mw, "_stop_yt_transport", lambda: events.append("proxy-stop"))
    mw.stop()
    assert events == ["proxy-stop", "player-stop", "player-close"]


def test_youtube_cover_extraction_matches_release_behavior():
    """Verified v5.0.0 behavior: the cover worker runs for every source.

    A guard that skipped it for YouTube shipped in a build that regressed
    against the verified release; cover extraction is part of the proven
    playback flow and must not be conditionally disabled.
    """
    import inspect

    source = inspect.getsource(MainWindow._open_external_source)
    assert "cover_source = str(source)" in source
    assert "threading.Thread(target=cover_worker" in source
    assert "second full-stream consumer" not in source


def test_youtube_routes_to_streaming_path_not_download(app, mw, monkeypatch):
    """Every YouTube entry point must stream via _play_youtube, never download."""
    assert not hasattr(MainWindow, "_download_media")
    played = []
    monkeypatch.setattr(
        mw, "_play_youtube",
        lambda url, *, label="": played.append((url, label)),
    )
    real_settings = mw.settings_store.load()
    monkeypatch.setattr(
        mw.settings_store, "load",
        lambda: replace(real_settings, ytdlp_consent=True),
    )
    mw._resolve_and_open_external_source(
        "https://www.youtube.com/watch?v=xyz123", display_label="Titel")
    assert played == [("https://www.youtube.com/watch?v=xyz123", "Titel")]


def test_no_second_player_remains(mw):
    """No QWebEngineView overlay, no JS player state, no browser fallback."""
    assert not hasattr(mw, "_youtube_view")
    assert not hasattr(MainWindow, "_open_web_video")
    assert not hasattr(MainWindow, "_on_yt_js")
    assert "webbrowser" not in vars(mw_module)
    assert "QWebEngineView" not in vars(mw_module)
    assert not hasattr(MainWindow, "_hide_web_video")
    assert hasattr(MainWindow, "_stop_yt_transport")
    assert "stop_youtube" in (MainWindow.stop.__kwdefaults__ or {})
    # The proxy is pure byte transport: no HTML player page, no yt-dlp,
    # no player_client selection of its own.
    from mpcasu_qt import youtube_proxy
    assert not hasattr(youtube_proxy.YouTubeMediaProxy, "_PLAYER_HTML")
    assert not hasattr(youtube_proxy, "shutil")
    assert not hasattr(youtube_proxy, "subprocess")


def test_video_mode_hides_caption_and_badges(app, mw):
    """Qt overlays must never sit above the native libVLC video surface."""
    mw._audio_stage = False
    mw._set_caption("Titel", Path("/x/test.mp4"))
    app.processEvents()
    assert mw._caption_label.isHidden()
    assert mw._badges_label.isHidden()


def test_audio_mode_keeps_caption_and_badges(app, mw):
    """Audio mode may keep caption/badges (no native video surface)."""
    mw._audio_stage = True
    mw._set_caption("Track", Path("/x/track.mp3"))
    app.processEvents()
    assert not mw._caption_label.isHidden()
    assert not mw._badges_label.isHidden()


def test_play_selected_video_hides_overlays(app, mw, monkeypatch, tmp_path):
    """Starting a normal video must hide caption/badges before playback."""
    monkeypatch.setattr(mw_module, "LibVLCBackend", _StubBackend)
    video = tmp_path / "clip.mp4"
    video.write_bytes(
        b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42mp42" + b"\x00" * 128
    )
    mw.playlist_model.add([str(video)])
    mw.play_selected()
    app.processEvents()
    assert mw.backend is not None
    assert mw._caption_label.isHidden()
    assert mw._badges_label.isHidden()


def test_now_playing_heading_stays_fixed(mw):
    """'NOW PLAYING' is a fixed heading; titles go to their own label."""
    bar = mw._now_playing_bar
    bar.set_now_playing("Never Gonna Give You Up")
    assert bar.title_label.text() == "NOW PLAYING"
    assert bar.media_title_label.text() == "Never Gonna Give You Up"
    bar.set_now_playing("")
    assert bar.title_label.text() == "NOW PLAYING"
    assert bar.media_title_label.isHidden()
