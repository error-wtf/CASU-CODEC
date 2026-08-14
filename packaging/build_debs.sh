#!/usr/bin/env bash
# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
set -euo pipefail
export SOURCE_DATE_EPOCH=0
root=$(cd "$(dirname "$0")/.." && pwd)
version=1.0.0-rc9
out="$root/dist"
rm -rf "$out"; mkdir -p "$out"

make_pkg() {
  local name="$1" description="$2" depends="$3"; shift 3
  local stage="$out/stage-$name"
  rm -rf "$stage"; mkdir -p "$stage/DEBIAN"
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
  # Bytecode is host/interpreter-specific and mutates on first execution,
  # which would make an otherwise clean installation fail dpkg --verify.
  find "$stage" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
  find "$stage" -depth -type d -name '__pycache__' -empty -delete
  # Normalize archive metadata so identical inputs produce identical packages.
  find "$stage" -exec touch -h -d '@0' {} +
  dpkg-deb --build --root-owner-group "$stage" "$out/${name}_${version}_all.deb" >/dev/null
  rm -rf "$stage"
}

install_codec() {
  local stage="$1"; mkdir -p "$stage/usr/share/casu-codec" "$stage/usr/bin" "$stage/usr/share/icons/hicolor/256x256/apps"
  cp -a "$root/casu" "$root/LICENSE" "$root/README.md" \
    "$root/CASU_FORMAT_SPECIFICATION.md" "$root/ROADMAP_60_STEPS.md" \
    "$root/RELEASE_GATE_STATUS.json" "$root/THIRD_PARTY_COMPONENTS.md" \
    "$root/SOURCE_PROVENANCE.md" "$root/BUNDLED_CODEC_MATRIX.md" \
    "$root/THIRD_PARTY_LICENSES" "$root/docs" "$root/assets" "$root/web" \
    "$stage/usr/share/casu-codec/"
  cp "$root/assets/casu_codec_icon.png" "$stage/usr/share/icons/hicolor/256x256/apps/casu-codec.png"
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
  cp "$root/mpcasu_player.py" "$root/mpcasu_backend.py" "$root/mpcasu_native_backend.py" "$root/mpcasu_playback.py" "$root/MPCASU_IMPLEMENTATION_AUDIT.md" "$root/MPCASU_FEATURE_COMPLETION_MATRIX.md" "$stage/usr/share/casu-codec/"
  cp "$root/packaging/mpcasu.desktop" "$stage/usr/share/applications/mpcasu.desktop"
  cp "$root/assets/mpcasu_player_icon.png" "$stage/usr/share/icons/hicolor/256x256/apps/mpcasu-player.png"
  cat > "$stage/usr/bin/mpcasu" <<'EOF'
#!/bin/sh
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/usr/share/casu-codec${PYTHONPATH:+:$PYTHONPATH}
exec /usr/bin/python3 /usr/share/casu-codec/mpcasu_player.py "$@"
EOF
  chmod 0755 "$stage/usr/bin/mpcasu"
}
install_webplayer() {
  local stage="$1"; mkdir -p "$stage/usr/share/casu-codec" "$stage/usr/bin" "$stage/usr/share/applications" "$stage/usr/share/icons/hicolor/256x256/apps"
  cp "$root/web_casu.py" "$stage/usr/share/casu-codec/"
  cp "$root/packaging/web-casu.desktop" "$stage/usr/share/applications/web-casu.desktop"
  cp "$root/assets/mpcasu_player_icon.png" "$stage/usr/share/icons/hicolor/256x256/apps/web-casu.png"
  cat > "$stage/usr/bin/web-casu" <<'EOF'
#!/bin/sh
export PYTHONDONTWRITEBYTECODE=1
exec /usr/bin/python3 /usr/share/casu-codec/web_casu.py "$@"
EOF
  chmod 0755 "$stage/usr/bin/web-casu"
}

install_qtplayer() {
  local stage="$1"; mkdir -p "$stage/usr/share/casu-codec" "$stage/usr/bin" "$stage/usr/share/applications" "$stage/usr/share/icons/hicolor/256x256/apps"
  cp -a "$root/mpcasu_qt" "$stage/usr/share/casu-codec/"
  cp "$root/packaging/mpcasu.desktop" "$stage/usr/share/applications/mpcasu-qt.desktop"
  sed -i 's|^Exec=.*|Exec=mpcasu-qt %U|; s|^Name=.*|Name=MPCASU Qt|' "$stage/usr/share/applications/mpcasu-qt.desktop"
  cp "$root/assets/mpcasu_player_icon.png" "$stage/usr/share/icons/hicolor/256x256/apps/mpcasu-qt.png"
  cat > "$stage/usr/bin/mpcasu-qt" <<'EOF'
#!/bin/sh
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/usr/share/casu-codec${PYTHONPATH:+:$PYTHONPATH}
exec /usr/bin/python3 -m mpcasu_qt.app "$@"
EOF
  chmod 0755 "$stage/usr/bin/mpcasu-qt"
}

make_pkg casu-codec "CASU Codec for All Segmented Units" "python3 (>= 3.10), python3-numpy, python3-av (>= 14), ffmpeg" install_codec
make_pkg casu-converter "CASU full graphical audio video and CASU converter" "casu-codec (= $version), python3-tk" install_converter
make_pkg mpcasu "MPCASU CASU and legacy media player" "casu-codec (= $version), python3-tk, libvlc5, vlc-plugin-base, vlc-plugin-video-output, libpulse0, libass9, yt-dlp" install_player
make_pkg mpcasu-qt "MPCASU Qt desktop player (official red/black design system)" "casu-codec (= $version), mpcasu (= $version), python3-pyside6.qtcore, python3-pyside6.qtgui, python3-pyside6.qtwidgets, libvlc5" install_qtplayer
make_pkg web-casu "MPCASU local web media player" "casu-codec (= $version), python3 (>= 3.10)" install_webplayer
cd "$out"
sha256sum ./*.deb | sed 's# \./# #' > SHA256SUMS
printf 'Built CASU/MPCASU Debian packages version %s in %s\n' "$version" "$out"
