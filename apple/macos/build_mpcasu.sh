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
  --add-data 'assets:assets' mpcasu_player.py
codesign --verify --deep --strict --verbose=2 dist/MPCASU.app
QT_QPA_PLATFORM=offscreen dist/MPCASU.app/Contents/MacOS/MPCASU \
  >"$OUT/macos-launch.log" 2>&1 &
app_pid=$!
sleep 8
if ! kill -0 "$app_pid" 2>/dev/null; then
  cat "$OUT/macos-launch.log"
  exit 1
fi
kill "$app_pid"
wait "$app_pid" 2>/dev/null || true
echo "MACOS_PACKAGED_APP_SMOKE=PASS"
ditto -c -k --keepParent dist/MPCASU.app "$OUT/MPCASU-macOS-7.0.0.zip"
shasum -a 256 "$OUT/MPCASU-macOS-7.0.0.zip" > "$OUT/MPCASU-macOS-7.0.0.zip.sha256"

# Produce the real macOS distribution container and verify its contents by
# mounting it. Production signing/notarization is a separate credential gate.
dmg_stage="$(mktemp -d "$OUT/.dmg-stage.XXXXXX")"
mount_point="$(mktemp -d "$OUT/.dmg-mount.XXXXXX")"
trap 'hdiutil detach "$mount_point" -quiet 2>/dev/null || true; rm -rf "$dmg_stage" "$mount_point"' EXIT
ditto dist/MPCASU.app "$dmg_stage/MPCASU.app"
ln -s /Applications "$dmg_stage/Applications"
hdiutil create -quiet -volname "MPCASU 7.0.0" -srcfolder "$dmg_stage" \
  -ov -format UDZO "$OUT/MPCASU-macOS-7.0.0.dmg"
hdiutil attach -quiet -readonly -nobrowse -mountpoint "$mount_point" \
  "$OUT/MPCASU-macOS-7.0.0.dmg"
test -d "$mount_point/MPCASU.app"
test -L "$mount_point/Applications"
codesign --verify --deep --strict --verbose=2 "$mount_point/MPCASU.app"
hdiutil detach "$mount_point" -quiet
shasum -a 256 "$OUT/MPCASU-macOS-7.0.0.dmg" > "$OUT/MPCASU-macOS-7.0.0.dmg.sha256"
echo "MACOS_DMG=PASS"
