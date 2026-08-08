#!/usr/bin/env bash
# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
set -euo pipefail
export SOURCE_DATE_EPOCH=0
root=$(cd "$(dirname "$0")/.." && pwd)
version=1.0.0
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
  # Normalize archive metadata so identical inputs produce identical packages.
  find "$stage" -exec touch -h -d '@0' {} +
  dpkg-deb --build --root-owner-group "$stage" "$out/${name}_${version}_all.deb" >/dev/null
  rm -rf "$stage"
}

install_codec() {
  local stage="$1"; mkdir -p "$stage/usr/share/casu-codec" "$stage/usr/bin"
  cp -a "$root/casu" "$root/LICENSE" "$root/docs" "$stage/usr/share/casu-codec/"
  cat > "$stage/usr/bin/casu" <<'EOF'
#!/bin/sh
export PYTHONPATH=/usr/share/casu-codec${PYTHONPATH:+:$PYTHONPATH}
exec python3 -m casu "$@"
EOF
  chmod 0755 "$stage/usr/bin/casu"
}
install_converter() {
  local stage="$1"; mkdir -p "$stage/usr/share/casu-codec" "$stage/usr/bin"
  cp "$root/casu_converter.py" "$stage/usr/share/casu-codec/"
  cat > "$stage/usr/bin/casu-converter" <<'EOF'
#!/bin/sh
export PYTHONPATH=/usr/share/casu-codec${PYTHONPATH:+:$PYTHONPATH}
exec python3 -m casu_converter "$@"
EOF
  chmod 0755 "$stage/usr/bin/casu-converter"
}
install_player() {
  local stage="$1"; mkdir -p "$stage/usr/share/casu-codec" "$stage/usr/bin"
  cp "$root/mpcasu_player.py" "$root/mpcasu_backend.py" "$root/mpcasu_playback.py" "$root/MPCASU_IMPLEMENTATION_AUDIT.md" "$root/MPCASU_FEATURE_COMPLETION_MATRIX.md" "$stage/usr/share/casu-codec/"
  if [ -d "$root/assets" ]; then cp -a "$root/assets" "$stage/usr/share/casu-codec/"; fi
  cat > "$stage/usr/bin/mpcasu" <<'EOF'
#!/bin/sh
export PYTHONPATH=/usr/share/casu-codec${PYTHONPATH:+:$PYTHONPATH}
exec python3 /usr/share/casu-codec/mpcasu_player.py "$@"
EOF
  chmod 0755 "$stage/usr/bin/mpcasu"
}

make_pkg casu-codec "CASU Codec for All Segmented Units" "python3 (>= 3.10), python3-numpy, ffmpeg" install_codec
make_pkg casu-converter "CASU graphical media converter" "casu-codec (= $version), python3-tk" install_converter
make_pkg mpcasu "MPCASU CASU and legacy media player" "casu-codec (= $version), python3-tk, libvlc5" install_player
sha256sum "$out"/*.deb > "$out/SHA256SUMS"
printf 'Built CASU/MPCASU Debian packages version %s in %s\n' "$version" "$out"
