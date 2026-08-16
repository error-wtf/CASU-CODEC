# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Headless smoke for the Qt player in-window sources view.

Verifies (no network, no popups):
- SOURCES nav items exist (YOUTUBE / SPOTIFY / WEB & STREAMS)
- navigation switches the center stack to the in-window SourcesView
- consent banner visible until accepted, then persisted to settings.json
- search worker fills the result list (yt-dlp mocked)
- result activation resolves (mocked) and hands the loopback transport URL
  to the normal libVLC external-source pipeline
- Escape / back button return to the player page
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

tmp = tempfile.mkdtemp(prefix="mpcasu-qt-smoke-")
os.environ["XDG_CONFIG_HOME"] = tmp

from PySide6.QtWidgets import QApplication  # noqa: E402

import mpcasu_qt.main_window as mw  # noqa: E402
from casu.search import SearchResult  # noqa: E402

issues: list[str] = []


def check(name: str, ok: bool):
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    if not ok:
        issues.append(name)


def main() -> int:
    app = QApplication([])
    window = mw.MainWindow()
    window.show()
    app.processEvents()

    nav_names = [str(b.property("nav_name")) for b in window._sidebar._nav_buttons]
    check("SOURCES nav items present",
          {"YOUTUBE", "SPOTIFY", "WEB & STREAMS"} <= set(nav_names))

    window._navigate("YOUTUBE")
    app.processEvents()
    check("YOUTUBE switches to in-window SourcesView",
          window._center_stack.currentWidget() is window._sources_view)
    check("consent banner visible before consent",
          window._sources_view._consent_frame.isVisible())

    window._sources_view._accept_consent()
    app.processEvents()
    settings_file = Path(tmp) / "mpcasu" / "settings.json"
    payload = json.loads(settings_file.read_text(encoding="utf-8"))
    check("consent persisted to settings.json",
          payload.get("player", {}).get("ytdlp_consent") is True)
    check("consent banner hidden after consent",
          window._sources_view._consent_frame.isHidden())

    fake = [SearchResult(title=f"Result {i}", url=f"https://www.youtube.com/watch?v=fake{i}",
                         duration=60.0 + i, uploader="channel", source="youtube")
            for i in range(3)]
    import casu.search as search_mod
    search_mod.search_youtube = lambda query, limit=12, timeout=30.0: list(fake)

    window._sources_view._entry.setText("never gonna give you up")
    window._sources_view._run_search("never gonna give you up")
    for _ in range(100):
        app.processEvents()
        if window._sources_view._list.count():
            break
        import time
        time.sleep(0.05)
    check("search worker filled result list (mocked yt-dlp)",
          window._sources_view._list.count() == 3)

    check("real _open_external_source returns to player page",
          "_show_player_page" in mw.MainWindow._open_external_source.__code__.co_names)

    opened: list[tuple] = []

    def fake_open(source, display_label=None, **kwargs):
        window._show_player_page()
        opened.append((source, display_label, kwargs))
    window._open_external_source = fake_open
    mw.resolve_media_location = lambda value, timeout_seconds=30.0: value
    # Keep the smoke hermetic: the loopback transport is stubbed, so no real
    # yt-dlp resolve and no upstream fetch happen here.
    window._yt_stream.start = lambda resolved, **kw: "http://127.0.0.1:9/SECRET/media"
    window._sources_view._play_row(1)
    for _ in range(200):
        app.processEvents()
        if opened:
            break
        import time
        time.sleep(0.05)
    check("result activation resolved and opened (mocked)",
          opened and opened[0][0] == "http://127.0.0.1:9/SECRET/media"
          and opened[0][1] == "Result 1"
          and opened[0][2].get("youtube") is True)
    check("player page restored after activation",
          window._center_stack.currentIndex() == 0)

    window._navigate("WEB & STREAMS")
    app.processEvents()
    check("WEB & STREAMS opens url mode in-window",
          window._center_stack.currentWidget() is window._sources_view
          and window._sources_view._mode == "url")
    window._sources_view._entry.setText("https://ice.bassdrive.net/stream")
    window._resolve_and_open_external_source("https://ice.bassdrive.net/stream")
    check("direct url path reaches resolve worker",
          window._resolve_generation >= 1)

    window._sources_view.closeRequested.emit()
    app.processEvents()
    check("back action returns to player page",
          window._center_stack.currentIndex() == 0)

    check("no QMessageBox popups left in main_window",
          not hasattr(mw, "QMessageBox"))

    window.close()
    app.processEvents()
    print(f"smoke_qt_sources: {'PASS' if not issues else 'FAIL'} ({len(issues)} issues)")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
