# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Desktop acceptance matrix — exercises the INSTALLED Qt player.

Run with the installed package on PYTHONPATH:
    PYTHONPATH=/usr/share/casu-codec python3 tools/acceptance_qt.py
Every step prints [OK]/[FAIL]; exit code 0 only if all pass.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp(prefix="mpcasu-acc-"))
ROOT = Path(__file__).resolve().parent.parent
MEDIA = ROOT / "test_media"
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QFileDialog, QPushButton  # noqa: E402
from PySide6.QtCore import QTimer, Qt  # noqa: E402

import mpcasu_qt.main_window as mw  # noqa: E402

RESULTS: list[tuple[str, bool]] = []


def check(name: str, ok: bool):
    RESULTS.append((name, bool(ok)))
    print(f"[{'OK' if ok else 'FAIL'}] {name}", flush=True)


def play_until(w, seconds=1.0, timeout=20.0) -> float:
    t0 = time.time()
    pos = 0.0
    while time.time() - t0 < timeout:
        QApplication.processEvents()
        if w.backend is not None:
            try:
                pos = max(pos, w.backend.position())
            except Exception:
                pass
        if pos > seconds:
            break
        time.sleep(0.1)
    return pos


def main() -> int:
    # QtWebEngine refuses to start as root without --no-sandbox (mirrors
    # the policy applied in mpcasu_qt.app.main).
    if hasattr(os, "getuid") and os.getuid() == 0:
        _flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        if "--no-sandbox" not in _flags:
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (_flags + " --no-sandbox").strip()
    app = QApplication([])
    w = mw.MainWindow()
    w.show()
    app.processEvents()
    check("window opens", w.isVisible())

    # MP4 playback + centered stage geometry
    w.add_files([MEDIA / "demo_clip.mp4"])
    app.processEvents()
    w._playlist_pane.select_row(0)
    w.play_selected()
    pos = play_until(w)
    check("mp4 plays >1s", pos > 1.0)
    stage = w._video_surface
    check("stage is visual center (width majority)",
          stage.width() > 2.2 * w._sidebar.width())

    # pause/resume
    w.toggle_playback(); app.processEvents()
    p1 = w.backend.position(); time.sleep(0.7); app.processEvents()
    p2 = w.backend.position()
    check("pause holds position", abs(p2 - p1) < 0.3)
    w.toggle_playback(); app.processEvents()

    # seek
    w.seek_by(2)
    t0 = time.time(); sought = 0
    while time.time() - t0 < 8:
        app.processEvents(); sought = w.backend.position()
        if sought >= 1.5: break
        time.sleep(0.1)
    check("seek advances", sought >= 1.5)

    # fullscreen enter/exit via real window state
    w.toggle_fullscreen(); app.processEvents()
    check("fullscreen enters", w.isFullScreen())
    w.toggle_fullscreen(); app.processEvents()
    check("fullscreen exits", not w.isFullScreen())

    # MP3 + visualizer
    w.add_files([MEDIA / "lino_casu_error.mp3"])
    app.processEvents()
    w._playlist_pane.select_row(w._playlist_pane.tree.topLevelItemCount() - 1)
    w.play_selected()
    pos = play_until(w, 1.0, 20)
    t0 = time.time()
    # 25 s budget: full-file PCM decode competes with desktop load.
    while time.time() - t0 < 25 and not w._visualizer.isVisible():
        app.processEvents(); time.sleep(0.2)
    check("mp3 plays >1s", pos > 1.0)
    check("visualizer visible with real bands",
          w._visualizer.isVisible() and len(w._visualizer._wave) > 0)

    # standalone CASUNAT2 (source absent from queue dir is irrelevant: file alone)
    w.add_files([MEDIA / "demo_casunat2.casu"])
    app.processEvents()
    w._playlist_pane.select_row(w._playlist_pane.tree.topLevelItemCount() - 1)
    w.play_selected()
    pos = play_until(w)
    check("casunat2 plays >1s", pos > 1.0)

    # CASUNAT1 envelope
    w.add_files([MEDIA / "demo_clip.mp4.casu"])
    app.processEvents()
    w._playlist_pane.select_row(w._playlist_pane.tree.topLevelItemCount() - 1)
    w.play_selected()
    pos = play_until(w, timeout=45.0)
    check("casunat1 envelope plays >1s", pos > 1.0)

    # MP5
    w.add_files([MEDIA / "demo.mp5"])
    app.processEvents()
    w._playlist_pane.select_row(w._playlist_pane.tree.topLevelItemCount() - 1)
    w.play_selected()
    pos = play_until(w, timeout=45.0)
    check("mp5 plays >1s", pos > 1.0)

    # playlist: newly added playlist expanded by default + child playback
    w.add_files([MEDIA / "demo_playlist.m3u"])
    app.processEvents()
    tree = w._playlist_pane.tree
    pl_item = None
    for i in range(tree.topLevelItemCount()):
        if str(tree.topLevelItem(i).data(0, Qt.UserRole)).endswith(".m3u"):
            pl_item = tree.topLevelItem(i)
    check("playlist added", pl_item is not None)
    check("new playlist expanded by default", pl_item is not None and pl_item.isExpanded())
    check("playlist children loaded", pl_item is not None and pl_item.childCount() >= 1
          and pl_item.child(0).text(0) != "…")

    # choose files dialog opens and cancels cleanly
    opened = []
    def close_dialog():
        for d in app.topLevelWidgets():
            if isinstance(d, QFileDialog):
                opened.append(True)
                d.close()
    QTimer.singleShot(1000, close_dialog)
    choose = [b for b in w._playlist_pane.findChildren(QPushButton)
              if b.text() == "Choose files"][0]
    choose.click()
    t0 = time.time()
    while time.time() - t0 < 4:
        app.processEvents(); time.sleep(0.05)
    check("choose-files dialog opens", bool(opened))
    choose.click()
    QTimer.singleShot(1000, close_dialog)
    t0 = time.time()
    opened.clear()
    while time.time() - t0 < 4:
        app.processEvents(); time.sleep(0.05)
    check("choose-files reopens after cancel", bool(opened))

    # URL flow: network stream plays
    w.show_sources("url")
    app.processEvents()
    w._sources_view._entry.setText("https://ice.bassdrive.net/stream")
    w._sources_view._open_typed()
    pos = play_until(w, 1.0, 30)
    check("internet stream plays >1s", pos > 1.0)

    # escape returns to player page
    w.show_sources("youtube"); app.processEvents()
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent, Qt as QtC
    ev = QKeyEvent(QEvent.Type.KeyPress, QtC.Key_Escape, QtC.NoModifier)
    app.sendEvent(w, ev)
    app.processEvents()
    check("escape returns to player page", w._center_stack.currentIndex() == 0)

    # resize does not crush stage
    w.resize(1100, 700); app.processEvents()
    small_stage = w._video_surface.width()
    w.resize(1500, 900); app.processEvents()
    check("resize keeps stage dominant",
          w._video_surface.width() > small_stage * 0.5 and
          w._video_surface.width() > w._playlist_pane.width())

    w.close(); app.processEvents()
    failed = [n for n, ok in RESULTS if not ok]
    print(f"ACCEPTANCE QT: {len(RESULTS) - len(failed)}/{len(RESULTS)} passed",
          flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
