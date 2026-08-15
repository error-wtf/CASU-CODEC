# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""MPCASU Qt entry point.

Usage:
    python3 -m mpcasu_qt.app [media_file ...]
"""
from __future__ import annotations

import getpass
import os
import sys
import tempfile
import time
from pathlib import Path

# Ensure the project root is on sys.path so casu.* imports resolve.
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from mpcasu_qt.main_window import MainWindow
from PySide6.QtCore import QLockFile, QStandardPaths, Qt, QTimer
from PySide6.QtWidgets import QApplication, QMainWindow

try:
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    _HAVE_NETWORK = True
except ImportError:  # single-instance IPC is optional
    QLocalServer = QLocalSocket = None
    _HAVE_NETWORK = False


def _instance_id() -> str:
    if hasattr(os, "getuid"):
        return str(os.getuid())
    return getpass.getuser().replace("/", "_")


def _send_to_primary(server_name: str, paths) -> bool:
    payload = "\n".join(str(p) for p in paths).encode("utf-8")

    # Primary may own the lock but still be starting its IPC server.
    for _ in range(20):
        socket = QLocalSocket()
        socket.connectToServer(server_name)

        if socket.waitForConnected(100):
            socket.write(payload)
            socket.waitForBytesWritten(500)
            socket.disconnectFromServer()
            return True

        socket.abort()
        time.sleep(0.05)

    return False


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("MPCASU")
    app.setOrganizationName("Lino-Codec")
    app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings, True)

    paths = [Path(arg).expanduser() for arg in sys.argv[1:]]

    ident = _instance_id()
    server_name = f"mpcasu-{ident}"

    runtime = (
        QStandardPaths.writableLocation(QStandardPaths.RuntimeLocation)
        or tempfile.gettempdir()
    )

    lock = QLockFile(str(Path(runtime) / f"{server_name}.lock"))
    lock.setStaleLockTime(30_000)

    if not lock.tryLock(0):
        if _HAVE_NETWORK and _send_to_primary(server_name, paths):
            return 0
        print("MPCASU primary instance exists but IPC is unavailable",
              file=sys.stderr)
        return 2

    # We own the lock, therefore removing a stale IPC socket is safe here.
    server = None
    if _HAVE_NETWORK:
        QLocalServer.removeServer(server_name)
        server = QLocalServer(app)
        if not server.listen(server_name):
            print(f"MPCASU IPC failed: {server.errorString()}",
                  file=sys.stderr)
            lock.unlock()
            return 2

    window = MainWindow(initial=paths)

    if server is not None:
        def handle_connection():
            client = server.nextPendingConnection()
            if client is None:
                return

            if not client.waitForReadyRead(1000):
                client.disconnectFromServer()
                return

            data = bytes(client.readAll())
            client.disconnectFromServer()

            targets = [
                line.strip()
                for line in data.decode("utf-8", "replace").splitlines()
                if line.strip()
            ]

            if targets:
                window.add_files(targets)

            window.showNormal()
            window.raise_()
            window.activateWindow()

        server.newConnection.connect(handle_connection)

    window.show()
    QTimer.singleShot(500, _check_main_windows)
    result = app.exec()

    if server is not None:
        server.close()
    lock.unlock()
    return result


def _check_main_windows() -> None:
    """Hard guard: exactly one visible QMainWindow may ever exist."""
    mains = [
        widget for widget in QApplication.topLevelWidgets()
        if isinstance(widget, QMainWindow) and widget.isVisible()
    ]
    if len(mains) != 1:
        raise RuntimeError(
            f"MPCASU BUG: {len(mains)} visible QMainWindows: "
            + ", ".join(f"{type(w).__name__}:{w.windowTitle()}"
                        for w in mains)
        )


if __name__ == "__main__":
    raise SystemExit(main())
