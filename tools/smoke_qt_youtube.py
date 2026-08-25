# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
"""Live Qt/Linux YouTube smoke: resolver -> proxy -> libVLC must advance."""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

root = Path(__file__).resolve().parent.parent
if os.environ.get("MPCASU_SMOKE_INSTALLED") != "1":
    sys.path.insert(0, str(root))
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="mpcasu-qt-youtube-")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from mpcasu_qt.main_window import MainWindow  # noqa: E402

URL = os.environ.get(
    "MPCASU_YOUTUBE_SMOKE_URL",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
)

# QtWebEngine refuses to start as root without --no-sandbox; the smoke
# bypasses main() so the policy from mpcasu_qt.app must be mirrored here.
if hasattr(os, "getuid") and os.getuid() == 0:
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    if "--no-sandbox" not in flags:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (flags + " --no-sandbox").strip()

QApplication.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings, True)
app = QApplication([])
window = MainWindow()
window.show()
app.processEvents()
window._play_youtube(URL, label="MPCASU YouTube live smoke")

deadline = time.monotonic() + 60.0
position = duration = 0.0
states: list[str] = []
while time.monotonic() < deadline:
    app.processEvents()
    backend = window.backend
    if backend is not None:
        try:
            position = float(backend.position())
            duration = float(backend.duration())
            state = str(getattr(backend.state(), "value", backend.state()))
            if not states or states[-1] != state:
                states.append(state)
        except Exception:
            pass
        if position > 1.0 and duration > position:
            break
    time.sleep(0.05)

ok = position > 1.0 and duration > position
snapshot = Path(os.environ["XDG_CONFIG_HOME"]) / "youtube-frame.png"
snapshot_ok = False
if ok and window.backend is not None:
    try:
        window.backend.take_snapshot(snapshot)
        snap_deadline = time.monotonic() + 5.0
        while time.monotonic() < snap_deadline and not snapshot.is_file():
            app.processEvents()
            time.sleep(0.05)
        if snapshot.is_file():
            from PySide6.QtGui import QImage
            image = QImage(str(snapshot))
            snapshot_ok = (not image.isNull() and image.width() > 0
                           and image.height() > 0 and snapshot.stat().st_size > 1024)
    except Exception as exc:
        print(f"[FAIL] Qt YouTube snapshot: {exc}")
ok = ok and snapshot_ok
print(
    f"[{'OK' if ok else 'FAIL'}] Qt YouTube position={position:.2f}s "
    f"duration={duration:.2f}s states={states} snapshot={snapshot_ok}"
)
window.close()
app.processEvents()
print(f"smoke_qt_youtube: {'PASS' if ok else 'FAIL'}")
raise SystemExit(0 if ok else 1)
