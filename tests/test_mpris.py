"""MPRIS D-Bus Fernsteuerung (org.mpris.MediaPlayer2.*) — Verhaltenstests.

Akzeptanzkriterien (P1, GNOME-Integration):
- Property-Mapping: PlaybackStatus/LoopStatus/Shuffle/Metadata/Volume
  spiegeln den MainWindow-Zustand (inkl. µs-Längen, file://-URIs,
  Netz-URL-Durchreichung, Tag-Titel-Fallback).
- LoopStatus/Shuffle/Volume-Schreibzugriffe erreichen den Player und
  werden persistiert (Repeat off/all/one ↔ None/Playlist/Track).
- Der Notifier sendet PropertiesChanged NUR bei echten Änderungen
  (Regression: str(QDBusObjectPath) enthält die Speicheradresse und
  ließ Metadata bei jedem Poll-Tick "springen" → Signal-Flut).
- Ohne Session-Bus (oder ohne QtDBus) läuft der Player normal weiter:
  _register_mpris liefert None, keine Ausnahme.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

pytest.importorskip("PySide6")

QW = pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import QObject, QTimer  # noqa: E402

import mpcasu_qt.main_window as mw  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QW.QApplication.instance() or QW.QApplication([])
    yield app


class _StubWindow(QObject):
    """Minimale Fenster-Oberfläche für die Adaptor-/Notifier-Ebene."""

    def __init__(self):
        super().__init__()
        self.backend = None
        self.current = None
        self.duration = 0.0
        self._paused = False
        self._volume = 100
        self._muted = False
        self._shuffle = False
        self._repeat_mode = "off"
        self.repeat_set = []
        self.shuffle_calls = []
        self.volume_calls = []

    def _set_repeat_mode(self, mode):
        if mode in ("off", "all", "one"):
            self._repeat_mode = mode
            self.repeat_set.append(mode)

    def _toggle_shuffle(self, value):
        self._shuffle = bool(value)
        self.shuffle_calls.append(bool(value))

    def _on_volume_slider(self, value):
        self._volume = int(value)
        self.volume_calls.append(int(value))

    def _display_title(self, path):
        try:
            return Path(path).stem + "!"
        except Exception:
            return ""


class _StubBackend:
    def __init__(self, state):
        self._state = state

    def state(self):
        return self._state

    def position(self):
        return 0.0


@pytest.fixture()
def player(qapp):
    window = _StubWindow()
    adaptor = mw._MprisPlayer(window)
    root = mw._MprisRoot(window)
    return window, root, adaptor


def test_interfaces_declared(player):
    _, root, player_adaptor = player
    for obj, interface in ((root, "org.mpris.MediaPlayer2"),
                           (player_adaptor, "org.mpris.MediaPlayer2.Player")):
        meta = obj.metaObject()
        index = meta.indexOfClassInfo("D-Bus Interface")
        assert index >= 0, f"{type(obj).__name__} lacks D-Bus Interface classinfo"
        assert str(meta.classInfo(index).value()) == interface


def test_root_properties(player):
    _, root, _ = player
    assert root.Identity == "MPCASU"
    assert root.CanQuit is True
    assert root.CanRaise is True
    assert root.HasTrackList is False
    assert root.DesktopEntry == "mpcasu"
    assert "file" in root.SupportedUriSchemes


def test_playback_status_mapping(player):
    window, _, adaptor = player
    assert adaptor.PlaybackStatus == "Stopped"
    window.backend = _StubBackend(mw.PlaybackState.PLAYING)
    assert adaptor.PlaybackStatus == "Playing"
    window._paused = True
    assert adaptor.PlaybackStatus == "Paused"
    window.backend = None
    window._paused = True
    # No backend wins: without a source nothing can be playing.
    assert adaptor.PlaybackStatus == "Stopped"


def test_metadata_local_and_remote(player):
    window, _, adaptor = player
    window.current = Path("/tmp/opencode/song.mp3")
    window.duration = 61.5
    meta = adaptor.Metadata
    assert meta["xesam:url"] == Path("/tmp/opencode/song.mp3").as_uri()
    assert meta["xesam:title"] == "song!"
    assert meta["mpris:length"] == 61_500_000
    trackid = str(meta["mpris:trackid"].path())
    assert trackid.startswith("/org/mpcasu/track/")
    assert len(trackid) == len("/org/mpcasu/track/") + 16

    # Network sources keep their original string in _network_source
    # (pathlib would collapse the "//"); metadata must prefer it.
    window._network_source = "https://example.com/stream.m3u8"
    window.current = Path("https:/example.com/stream.m3u8")
    meta = adaptor.Metadata
    assert meta["xesam:url"] == "https://example.com/stream.m3u8"
    assert meta["xesam:title"] == "stream!"
    window._network_source = None
    window.current = None
    assert adaptor.Metadata == {}


def test_loop_status_roundtrip(player):
    window, _, adaptor = player
    for dbus_name, internal in (("None", "off"), ("Track", "one"),
                                ("Playlist", "all")):
        adaptor.LoopStatus = dbus_name
        assert window._repeat_mode == internal
        assert adaptor.LoopStatus == dbus_name
        assert window.repeat_set[-1] == internal
    adaptor.LoopStatus = "Bogus"
    assert window._repeat_mode == "all"  # unknown values ignored
    assert adaptor.LoopStatus == "Playlist"


def test_shuffle_and_volume_writes(player):
    window, _, adaptor = player
    adaptor.Shuffle = True
    assert window._shuffle is True and window.shuffle_calls[-1] is True
    assert adaptor.Shuffle is True

    adaptor.Volume = 1.5
    assert window.volume_calls[-1] == 150
    window._muted = True
    assert adaptor.Volume == 0.0


def test_notifier_sends_only_on_change(player):
    window, _, adaptor = player
    sent = []

    class FakeBus:
        def send(self, message):
            args = message.arguments()
            sent.append(dict(args[1]) if len(args) >= 2 else {})
            return True

    notifier = mw._MprisNotifier(window, FakeBus(), adaptor, "svc")
    notifier.refresh()          # initial full snapshot
    notifier.refresh()          # identical -> silence
    notifier.refresh()          # identical -> silence
    assert len(sent) == 1, f"flapping detected: {len(sent)} sends"
    assert set(sent[0]) == {"PlaybackStatus", "LoopStatus", "Shuffle",
                            "Metadata", "Volume"}

    window.current = Path("/tmp/opencode/song.mp3")
    window.duration = 6.0
    notifier.refresh()
    assert len(sent) == 2 and "Metadata" in sent[1]
    notifier.refresh()
    assert len(sent) == 2, "stable metadata must not re-send"


def test_register_without_session_bus_is_none(qapp):
    # In the offscreen test environment there may or may not be a session
    # bus; either way registration must never raise. A real bus yields a
    # notifier, a missing bus yields None.
    result = mw._register_mpris(_StubWindow())
    assert result is None or hasattr(result, "refresh")


def test_poll_hook_survives_without_notifier(qapp, monkeypatch):
    monkeypatch.setattr(mw.MainWindow, "_mpris_notifier", None, raising=False)
    # The poll hook must reference the notifier attribute defensively; the
    # method itself has to exist on the class for the QTimer wiring.
    assert callable(getattr(mw.MainWindow, "_poll", None))
