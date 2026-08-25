#!/usr/bin/env bash
# PySide6-on-Android build for the real MPCASU (mpcasu_qt).
# PREREQUISITE (the only missing piece): PySide6 + shiboken6 ANDROID
# wheels (arm64-v8a, matching the host PySide6 version). They are not on
# PyPI/public mirrors — obtain via Qt Account (installer "PySide6 Android"
# component) or build from qt/pyside source. Place them in this folder.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

WHEEL_PYSIDE="${1:-}"
WHEEL_SHIBOKEN="${2:-}"
[ -x "$(command -v pyside6-android-deploy)" ] || { echo "pyside6-android-deploy fehlt"; exit 1; }
ls "$HERE"/PySide6-*android*.whl >/dev/null 2>&1 && WHEEL_PYSIDE="$(ls "$HERE"/PySide6-*android*.whl | head -1)"
ls "$HERE"/shiboken6-*android*.whl >/dev/null 2>&1 && WHEEL_SHIBOKEN="$(ls "$HERE"/shiboken6-*android*.whl | head -1)"
[ -n "$WHEEL_PYSIDE" ] && [ -n "$WHEEL_SHIBOKEN" ] || {
  echo "PySide6/shiboken6 ANDROID wheels fehlen (Qt-Account oder Selbstbau)."
  echo "Siehe README.md — Abschnitt 'Der fehlende Baustein'."
  exit 2; }

# Player sources into the deploy payload.
rm -rf src
mkdir -p src
cp -r ../mpcasu_qt src/
cp -r ../casu src/
cp -r ../mpcasu_backend.py ../mpcasu_native_backend.py ../mpcasu_playback.py ../web_casu.py src/ 2>/dev/null || true

export ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-/opt/android-sdk}"
export ANDROID_NDK_ROOT="${ANDROID_NDK_ROOT:-$ANDROID_SDK_ROOT/ndk/26.3.11579264}"

pyside6-android-deploy --name MPCASU --wheel-pyside "$WHEEL_PYSIDE" \
  --wheel-shiboken "$WHEEL_SHIBOKEN" --ndk-path "$ANDROID_NDK_ROOT" \
  --sdk-path "$ANDROID_SDK_ROOT" -f
echo "APK: build/…/MPCASU-android-arm64-v8a.apk (deploy tool output)"
