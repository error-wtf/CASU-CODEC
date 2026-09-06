#!/usr/bin/env bash
# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
set -euo pipefail
export SOURCE_DATE_EPOCH=0
root=$(cd "$(dirname "$0")/.." && pwd)
version=7.0.0
out="$root/dist"
mkdir -p "$out"
stage_root=$(mktemp -d "${TMPDIR:-/tmp}/casu-debs.XXXXXX")
trap 'rm -rf "$stage_root"' EXIT

make_pkg() {
  local name="$1" description="$2" depends="$3"; shift 3
  local stage="$stage_root/$name"
  mkdir -p "$stage/DEBIAN"
  cat > "$stage/DEBIAN/control" <<EOF
Package: $name
Version: $version
Section: video
Priority: optional
Architecture: all
Maintainer: Lino Casu <error-wtf@users.noreply.github.com>
Depends: $depends
Description: $description
 CASU/MPCASU legacy-compatible segmented media tools.
EOF
  "$@" "$stage"
  # Runtime bytecode caches survive dpkg upgrades (installed sources carry
  # mtime 0 for reproducibility, which makes stale .pyc files look valid).
  # Purge them on every install/upgrade so the shipped sources always win.
  cat > "$stage/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
find /usr/share/casu-codec -depth -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
# Register the application/x-casu MIME type so .casu/.mp5 files open with
# MPCASU in file managers / desktop environments (shared-mime-info).
if [ -f /usr/share/mime/packages/casu-codec-mime.xml ]; then
  update-mime-database /usr/share/mime >/dev/null 2>&1 || true
fi
# Refresh desktop entry caches so the new MimeType association takes effect.
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
fi
EOF
  chmod 0755 "$stage/DEBIAN/postinst"
  # Bytecode is host/interpreter-specific and mutates on first execution,
  # which would make an otherwise clean installation fail dpkg --verify.
  find "$stage" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
  find "$stage" -depth -type d -name '__pycache__' -empty -delete
  # Editor/session backups must never ship.
  find "$stage" -type f \( -name '*.bak' -o -name '*.bak2' -o -name '*.bak-*' -o -name '*~' \) -delete
  # Normalize archive metadata so identical inputs produce identical packages.
  find "$stage" -exec touch -h -d '@0' {} +
  dpkg-deb --build --root-owner-group "$stage" "$out/${name}_${version}_all.deb" >/dev/null
  rm -rf "$stage"
}

install_codec() {
  local stage="$1"; mkdir -p "$stage/usr/share/casu-codec" "$stage/usr/bin" "$stage/usr/share/icons/hicolor/256x256/apps" "$stage/usr/share/mime/packages"
  cp -a "$root/casu" "$root/LICENSE" "$root/README.md" \
    "$root/CASU_FORMAT_SPECIFICATION.md" "$root/ROADMAP_60_STEPS.md" \
    "$root/RELEASE_GATE_STATUS.json" "$root/THIRD_PARTY_COMPONENTS.md" \
    "$root/SOURCE_PROVENANCE.md" "$root/BUNDLED_CODEC_MATRIX.md" \
    "$root/THIRD_PARTY_LICENSES" "$root/docs" "$root/assets" "$root/web" \
    "$stage/usr/share/casu-codec/"
  cp "$root/assets/casu_codec_icon.png" "$stage/usr/share/icons/hicolor/256x256/apps/casu-codec.png"
  # MIME definition so .casu/.mp5 files are recognized as application/x-casu
  # and open with MPCASU in file managers / desktop environments.
  cp "$root/packaging/casu-codec-mime.xml" "$stage/usr/share/mime/packages/casu-codec-mime.xml"
  cat > "$stage/usr/bin/casu" <<'EOF'
#!/bin/sh
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/usr/share/casu-codec${PYTHONPATH:+:$PYTHONPATH}
exec /usr/bin/python3 -m casu "$@"
EOF
  chmod 0755 "$stage/usr/bin/casu"
}
install_converter() {
  local stage="$1"; mkdir -p "$stage/usr/share/casu-codec" "$stage/usr/bin" "$stage/usr/share/applications" "$stage/usr/share/icons/hicolor/256x256/apps"
  cp "$root/casu_converter.py" "$stage/usr/share/casu-codec/"
  cp "$root/packaging/casu-converter.desktop" "$stage/usr/share/applications/casu-converter.desktop"
  cp "$root/assets/casu_converter_icon.png" "$stage/usr/share/icons/hicolor/256x256/apps/casu-converter.png"
  cat > "$stage/usr/bin/casu-converter" <<'EOF'
#!/bin/sh
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/usr/share/casu-codec${PYTHONPATH:+:$PYTHONPATH}
exec /usr/bin/python3 -m casu_converter "$@"
EOF
  chmod 0755 "$stage/usr/bin/casu-converter"
}
install_player() {
  local stage="$1"; mkdir -p "$stage/usr/share/casu-codec" "$stage/usr/bin" "$stage/usr/share/applications" "$stage/usr/share/icons/hicolor/256x256/apps"
  cp -a "$root/mpcasu_qt" "$stage/usr/share/casu-codec/"
  cp "$root/mpcasu_backend.py" "$root/mpcasu_native_backend.py" "$root/mpcasu_playback.py" "$root/MPCASU_IMPLEMENTATION_AUDIT.md" "$root/MPCASU_FEATURE_COMPLETION_MATRIX.md" "$stage/usr/share/casu-codec/"
  cp "$root/packaging/mpcasu.desktop" "$stage/usr/share/applications/mpcasu.desktop"
  cp "$root/assets/mpcasu_player_icon.png" "$stage/usr/share/icons/hicolor/256x256/apps/mpcasu-player.png"
  cat > "$stage/usr/bin/mpcasu" <<'EOF'
#!/bin/sh
export PYTHONDONTWRITEBYTECODE=1
# Platform selection so the player runs on BOTH X11 and Wayland.
#
# The Qt player embeds libVLC via X11 (set_xwindow) and its VideoSurface uses
# WA_NativeWindow, which needs an X11 window id. On a Wayland session that
# embedding is only possible through XWayland. Instead of blindly forcing one
# platform (which hangs on the other), pick based on what the session offers:
#   - DISPLAY set (X11, or Wayland + XWayland)  -> use xcb so video embeds
#   - only Wayland (no XWayland)                -> use wayland (audio still
#     plays; native CASU video is Qt-rendered and fully supported)
# Never force a platform that is not present, otherwise the player hangs.
if [ -z "${QT_QPA_PLATFORM:-}" ]; then
  if [ -n "${DISPLAY:-}" ]; then
    export QT_QPA_PLATFORM=xcb
  else
    export QT_QPA_PLATFORM=wayland
  fi
fi
export PYTHONPATH=/usr/share/casu-codec${PYTHONPATH:+:$PYTHONPATH}
# Root/container environments cannot use the Chromium sandbox (QtWebEngine).
if [ "$(id -u)" = "0" ]; then
  export QTWEBENGINE_DISABLE_SANDBOX=1
fi
# Always run the INSTALLED package, regardless of the current directory.
cd /
exec /usr/bin/python3 -m mpcasu_qt.app "$@"
EOF
  chmod 0755 "$stage/usr/bin/mpcasu"
}
install_webplayer() {
  local stage="$1"; mkdir -p "$stage/usr/share/casu-codec" "$stage/usr/bin" "$stage/usr/share/applications" "$stage/usr/share/icons/hicolor/256x256/apps"
  cp "$root/web_casu.py" "$stage/usr/share/casu-codec/"
  cp "$root/packaging/web-casu.desktop" "$stage/usr/share/applications/web-casu.desktop"
  cp "$root/assets/web_casu_icon.png" "$stage/usr/share/icons/hicolor/256x256/apps/web-casu.png"
  cat > "$stage/usr/bin/web-casu" <<'EOF'
#!/bin/sh
export PYTHONDONTWRITEBYTECODE=1
exec /usr/bin/python3 /usr/share/casu-codec/web_casu.py "$@"
EOF
  chmod 0755 "$stage/usr/bin/web-casu"
}

install_qtplayer() {
  # Retired: the Qt player is now the official `mpcasu` package (see
  # install_player). Kept as a no-op reference so older call sites fail loudly
  # instead of silently building a fifth package.
  echo "install_qtplayer is retired; mpcasu now ships the Qt player" >&2
  return 1
}

make_pkg casu-codec "CASU Codec for All Segmented Units" "python3 (>= 3.10), python3-numpy, python3-av (>= 14), ffmpeg, yt-dlp" install_codec
make_pkg casu-converter "CASU full graphical audio video and CASU converter" "casu-codec (= $version), python3-tk" install_converter
make_pkg mpcasu "MPCASU CASU and legacy media player (Qt, official red/black design)" "casu-codec (= $version), python3-pyside6.qtcore, python3-pyside6.qtgui, python3-pyside6.qtwidgets, python3-pyside6.qtnetwork, python3-pyside6.qtwebenginewidgets, libvlc5, vlc-plugin-base, vlc-plugin-video-output, libpulse0, libass9, yt-dlp" install_player
make_pkg web-casu "MPCASU local web media player" "casu-codec (= $version), python3 (>= 3.10), yt-dlp" install_webplayer
cd "$out"
sha256sum ./*.deb | sed 's# \./# #' > SHA256SUMS
printf 'Built CASU/MPCASU Debian packages version %s in %s\n' "$version" "$out"
