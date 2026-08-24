"""Live-Stream-Zeitanzeige — Plattform-Parität (Web, Pure-Web, Android, Qt).

Akzeptanzkriterien:
- Live-Streams (duration = Infinity, z. B. Radio) zeigen nie
  "Infinity:NaN:NaN": der formatTime-Formatter beider App.js-Varianten
  (web-casu minified + pure-web expanded) liefert für nicht-endliche
  Werte "LIVE".
- Die Seek-Leiste pegelt bei Live-Streams nicht auf "voll" (der Wert
  wird nur bei endlicher Dauer gesetzt).
- Die Kopien sind synchron: web/app.js ≡ win-release web-backend,
  pure-web-release ≡ Android-Assets ≡ win-release web/pure.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

WEBCASU_COPIES = [
    ROOT / "web" / "app.js",
    ROOT / "win-release" / "apps" / "web-backend" / "web" / "app.js",
]
PUREWEB_COPIES = [
    ROOT / "pure-web-release" / "app.js",
    ROOT / "android" / "app" / "src" / "main" / "assets" / "web" / "app.js",
    ROOT / "win-release" / "web" / "pure" / "app.js",
]


def test_format_time_guards_nonfinite_webcasu():
    for path in WEBCASU_COPIES:
        src = path.read_text(encoding="utf-8")
        assert 'if(!Number.isFinite(seconds)) return "LIVE";' in src, path


def test_format_time_guards_nonfinite_pureweb():
    for path in PUREWEB_COPIES:
        src = path.read_text(encoding="utf-8")
        assert 'if (!Number.isFinite(Number(value))) return "LIVE";' in src, \
            path


def test_seek_bar_ignores_infinite_duration():
    needle = 'Number.isFinite(media.duration)?media.currentTime:0'
    for path in WEBCASU_COPIES:
        assert needle in path.read_text(encoding="utf-8"), path
    needle_pure = ("Number.isFinite(media.duration) ? media.currentTime : 0")
    for path in PUREWEB_COPIES:
        assert needle_pure in path.read_text(encoding="utf-8"), path


def test_app_js_copies_stay_in_sync():
    for group in (WEBCASU_COPIES, PUREWEB_COPIES):
        blobs = {path.read_bytes() for path in group}
        assert len(blobs) == 1, f"app.js copies diverged inside {group}"


def test_qt_player_labels_live_streams():
    src = (ROOT / "mpcasu_qt" / "main_window.py").read_text(encoding="utf-8")
    assert 'self._time_total.setText("LIVE")' in src
    assert "elif self._network_source:" in src


def test_windows_player_labels_live_streams():
    src = (ROOT / "win-release" / "apps" / "mpcasu" / "main_window.cpp"
           ).read_text(encoding="utf-8")
    assert 'QStringLiteral("LIVE")' in src
    assert 'current_source_.contains(QStringLiteral("://"))' in src
