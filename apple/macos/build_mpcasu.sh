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
python -m pip install --disable-pip-version-check yt-dlp

python - <<'PY'
from PySide6 import QtCore
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
app = QApplication([])
assert app.screens()
print(f"MACOS_QT=PASS Qt={QtCore.__version__}")
PY

python -m pytest -q tests/v7/shared tests/test_inapp_browser.py tests/test_youtube_playlist_groups.py
python -m PyInstaller --noconfirm --clean --windowed --name MPCASU \
  --add-data 'assets:assets' mpcasu_qt/app.py

mkdir -p dist/MPCASU.app/Contents/Helpers dist/MPCASU.app/Contents/Frameworks/FFmpeg
python -m PyInstaller --noconfirm --clean --onefile --name yt-dlp "$(command -v yt-dlp)"
cp dist/yt-dlp dist/MPCASU.app/Contents/Helpers/yt-dlp

# Homebrew's ffmpeg is dynamically linked. dylibbundler copies and rewrites
# only its concrete non-system dependencies so conversion, probing, recording
# and the Wave visualizer also work on a clean Mac.
cp "$(command -v ffmpeg)" dist/MPCASU.app/Contents/Helpers/ffmpeg
cp "$(command -v ffprobe)" dist/MPCASU.app/Contents/Helpers/ffprobe
dylibbundler -od -b -x dist/MPCASU.app/Contents/Helpers/ffmpeg \
  -d dist/MPCASU.app/Contents/Frameworks/FFmpeg \
  -p @executable_path/../Frameworks/FFmpeg
dylibbundler -od -b -x dist/MPCASU.app/Contents/Helpers/ffprobe \
  -d dist/MPCASU.app/Contents/Frameworks/FFmpeg \
  -p @executable_path/../Frameworks/FFmpeg
chmod +x dist/MPCASU.app/Contents/Helpers/*

# python-vlc is only bindings. Ship the real VLC runtime and plugins inside
# MPCASU.app so playback never depends on /Applications/VLC.app.
vlc_root=/Applications/VLC.app/Contents/MacOS
test -f "$vlc_root/lib/libvlc.dylib"
test -d "$vlc_root/plugins"
mkdir -p dist/MPCASU.app/Contents/Frameworks/VLC
ditto "$vlc_root/lib" dist/MPCASU.app/Contents/Frameworks/VLC/lib
ditto "$vlc_root/plugins" dist/MPCASU.app/Contents/Frameworks/VLC/plugins
codesign --force --deep --sign - dist/MPCASU.app
codesign --verify --deep --strict --verbose=2 dist/MPCASU.app

# Generate a tiny deterministic WAV and prove that the packaged application,
# using only its embedded VLC runtime, advances playback time.
smoke_wav="$OUT/macos-playback-smoke.wav"
python - "$smoke_wav" <<'PY'
import math, struct, sys, wave
with wave.open(sys.argv[1], "wb") as output:
    output.setnchannels(1); output.setsampwidth(2); output.setframerate(44100)
    output.writeframes(b"".join(struct.pack("<h", int(7000 * math.sin(2 * math.pi * 440 * i / 44100))) for i in range(88200)))
PY
QT_QPA_PLATFORM=offscreen MPCASU_PACKAGED_PLAYBACK_SMOKE="$smoke_wav" \
  dist/MPCASU.app/Contents/MacOS/MPCASU \
  >"$OUT/macos-launch.log" 2>&1 &
app_pid=$!
if ! wait "$app_pid"; then
  cat "$OUT/macos-launch.log"
  exit 1
fi
grep -q 'MACOS_PACKAGED_PLAYBACK_SMOKE=PASS' "$OUT/macos-launch.log"
echo "MACOS_PACKAGED_QT_PLAYBACK_SMOKE=PASS"
# The codec distribution also includes its converter and command-line codec.
cat > .v7-codec-entry.py <<'PYCODEC'
from casu.cli import main
raise SystemExit(main())
PYCODEC
cat > .v7-tool-runtime.py <<'PYRUNTIME'
import os, sys
from pathlib import Path
helpers = Path(sys.executable).resolve().parent.parent / "Helpers"
os.environ["PATH"] = str(helpers) + os.pathsep + os.environ.get("PATH", "")
PYRUNTIME
python -m PyInstaller --noconfirm --clean --windowed --name CASU-Converter \
  --runtime-hook .v7-tool-runtime.py --add-data 'assets:assets' casu_converter.py
python -m PyInstaller --noconfirm --clean --onefile --name casu .v7-codec-entry.py
mkdir -p dist/CASU-Converter.app/Contents/Helpers dist/CASU-Converter.app/Contents/Frameworks/FFmpeg
ditto dist/MPCASU.app/Contents/Helpers dist/CASU-Converter.app/Contents/Helpers
ditto dist/MPCASU.app/Contents/Frameworks/FFmpeg dist/CASU-Converter.app/Contents/Frameworks/FFmpeg
cp dist/casu dist/CASU-Converter.app/Contents/Helpers/casu
codesign --force --deep --sign - dist/CASU-Converter.app
codesign --verify --deep --strict dist/CASU-Converter.app
dist/casu --help > "$OUT/macos-codec-help.log"
mkdir -p "$OUT/codec-stage"
ditto dist/MPCASU.app "$OUT/codec-stage/MPCASU.app"
ditto dist/CASU-Converter.app "$OUT/codec-stage/CASU-Converter.app"
cp dist/casu "$OUT/codec-stage/casu"
ditto -c -k "$OUT/codec-stage" "$OUT/MPCASU-macOS-7.0.0.zip"
rm -rf "$OUT/codec-stage"
shasum -a 256 "$OUT/MPCASU-macOS-7.0.0.zip" > "$OUT/MPCASU-macOS-7.0.0.zip.sha256"

# Produce the real macOS distribution container and verify its contents by
# mounting it. Production signing/notarization is a separate credential gate.
dmg_stage="$(mktemp -d "$OUT/.dmg-stage.XXXXXX")"
mount_point="$(mktemp -d "$OUT/.dmg-mount.XXXXXX")"
trap 'hdiutil detach "$mount_point" -quiet 2>/dev/null || true; rm -rf "$dmg_stage" "$mount_point"' EXIT
ditto dist/MPCASU.app "$dmg_stage/MPCASU.app"
ditto dist/CASU-Converter.app "$dmg_stage/CASU-Converter.app"
cp dist/casu "$dmg_stage/casu"
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
