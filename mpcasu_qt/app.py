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

try:
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    _HAVE_NETWORK = True
except ImportError:  # single-instance guard is optional
    QLocalServer = QLocalSocket = None
    _HAVE_NETWORK = False


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("MPCASU")
    app.setOrganizationName("Lino-Codec")
    app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings, True)

    paths = [Path(arg).expanduser() for arg in sys.argv[1:]]

    server = None
    window = None
    if _HAVE_NETWORK:
        socket = QLocalSocket(app)
        socket.connectToServer("mpcasu-single-instance")
        if socket.waitForConnected(300):
            payload = "\n".join(str(p) for p in paths).encode("utf-8")
            socket.write(payload)
            socket.waitForBytesWritten(1000)
            socket.disconnectFromServer()
            return 0

        server = QLocalServer(app)
        QLocalServer.removeServer("mpcasu-single-instance")
        server.listen("mpcasu-single-instance")

    window = MainWindow(initial=paths)

    if server is not None:
        def _handle(client):
            data = bytes(client.readAll())
            client.disconnectFromServer()
            for line in data.decode("utf-8", "replace").splitlines():
                if line.strip():
                    window.add_files([line])
            window.raise_()
            window.activateWindow()

        def _on_connection():
            client = server.nextPendingConnection()
            if client is not None:
                client.readyRead.connect(lambda: _handle(client))

        server.newConnection.connect(_on_connection)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
