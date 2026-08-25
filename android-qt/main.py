# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
"""MPCASU on Android — entry point for the PySide6-on-Android port.

Runs the REAL Linux player (mpcasu_qt) with Android compatibility shims
installed first (ffprobe/ffmpeg replacement via JNI, app-private config
dirs, small-screen layout mode).
"""
import os
import sys
from pathlib import Path

# Android app dirs (set by the deploy wrapper; fall back gracefully).
APP_HOME = Path(os.environ.get("MPCASU_ANDROID_HOME", "/data/data/org.casu.mpcasu"))
os.environ.setdefault("XDG_CONFIG_HOME", str(APP_HOME / "config"))
os.environ.setdefault("XDG_CACHE_HOME", str(APP_HOME / "cache"))
os.environ.setdefault("HOME", str(APP_HOME))

sys.path.insert(0, str(Path(__file__).resolve().parent))

from shims import android_compat  # noqa: E402  (installs ffprobe/ffmpeg shims)
android_compat.install()


def main() -> int:
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv[:1])
    app.setApplicationName("MPCASU")
    app.setOrganizationName("Lino-Codec")

    from mpcasu_qt.main_window import MainWindow
    window = MainWindow(initial=[])
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
