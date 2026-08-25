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

media = root / "test_media" / "demo_clip.mp4"
if not media.is_file():
    media = root / "test_media" / "lino_lol_test_pattern.mp4"
if not media.is_file():
    print(f"smoke_qt_playback: SKIP (missing {media})")
    raise SystemExit(0)

# QtWebEngine refuses to start as root without --no-sandbox (mirrors
# the policy applied in mpcasu_qt.app.main).
if hasattr(os, "getuid") and os.getuid() == 0:
    _flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    if "--no-sandbox" not in _flags:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (_flags + " --no-sandbox").strip()
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
