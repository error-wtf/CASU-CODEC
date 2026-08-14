# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Qt player playback smoke — local MP4 must reach > 1 s position."""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="mpcasu-qt-play-")

from PySide6.QtWidgets import QApplication  # noqa: E402
from mpcasu_qt.main_window import MainWindow  # noqa: E402

media = root / "test_media" / "giancarlo.mp4"
if not media.is_file():
    print(f"smoke_qt_playback: SKIP (missing {media})")
    raise SystemExit(0)

app = QApplication([])
window = MainWindow()
window.show()
app.processEvents()

window.add_files([media])
window._playlist_pane.select_row(0)
window.play_selected()

deadline = time.time() + 15.0
position = 0.0
while time.time() < deadline:
    app.processEvents()
    if window.backend is not None:
        try:
            position = window.backend.position()
        except Exception:
            position = 0.0
        if position > 1.0:
            break
    time.sleep(0.05)

ok = position > 1.0
print(f"[{'OK' if ok else 'FAIL'}] Qt playback position {position:.2f} s (> 1 s required)")
window.close()
app.processEvents()
print(f"smoke_qt_playback: {'PASS' if ok else 'FAIL'}")
raise SystemExit(0 if ok else 1)
