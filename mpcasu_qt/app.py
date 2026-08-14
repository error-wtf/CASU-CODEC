# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""MPCASU Qt entry point.

Usage:
    python3 -m mpcasu_qt.app [media_file ...]
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

# Ensure the project root is on sys.path so casu.* imports resolve.
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from mpcasu_qt.main_window import MainWindow
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("MPCASU")
    app.setOrganizationName("Lino-Codec")
    app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings, True)

    paths = [Path(arg).expanduser() for arg in sys.argv[1:]]
    window = MainWindow(initial=paths)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
