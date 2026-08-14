# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Screenshot driver for the MPCASU Qt desktop player (runs under Xvfb)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp(prefix="mpcasu-shot-"))

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from mpcasu_qt.main_window import MainWindow  # noqa: E402

app = QApplication([])
window = MainWindow()
window.show()

media = root / "test_media"
window.add_files([
    media / "demo_clip.mp4",
    media / "demo_playlist.m3u",
    media / "demo_casunat2.casu",
    media / "demo.mp5",
])
tree = window._playlist_pane.tree
for index in range(tree.topLevelItemCount()):
    item = tree.topLevelItem(index)
    if str(item.data(0, Qt.UserRole)).endswith(".m3u"):
        item.setExpanded(True)
window._playlist_pane.select_row(0)
window.play_selected()
window.status("Playing demo_clip.mp4 · libVLC · queue edited in-place")

QTimer.singleShot(20000, app.quit)
raise SystemExit(app.exec())
