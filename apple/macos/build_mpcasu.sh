#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
OUT="${APPLE_OUTPUT_DIR:-$ROOT/dist/apple}"
mkdir -p "$OUT"

python3 -m venv .venv-v7-macos
source .venv-v7-macos/bin/activate
python -m pip install --disable-pip-version-check -U pip wheel setuptools
python -m pip install --disable-pip-version-check -e . 'PySide6==6.10.2' python-vlc pytest pytest-qt pyinstaller

python - <<'PY'
from PySide6 import QtCore
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
app = QApplication([])
assert app.screens()
print(f"MACOS_QT=PASS Qt={QtCore.__version__}")
PY

python -m pytest -q tests/v7/shared
python -m PyInstaller --noconfirm --clean --windowed --name MPCASU \
  --collect-all PySide6 --add-data 'assets:assets' mpcasu_player.py
ditto -c -k --keepParent dist/MPCASU.app "$OUT/MPCASU-macOS-7.0.0.zip"
codesign --verify --deep --strict --verbose=2 dist/MPCASU.app
shasum -a 256 "$OUT/MPCASU-macOS-7.0.0.zip" > "$OUT/MPCASU-macOS-7.0.0.zip.sha256"

