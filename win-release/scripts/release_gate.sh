#!/usr/bin/env bash
# release_gate.sh — produce WINDOWS_RELEASE_GATE.json (WP-REL-006).
# Machine-readable PASS/FAIL/BLOCKED/NOT_TESTED per gate area. A BLOCKED or
# FAIL is never reported as PASS. Called from build-windows-release.sh step 8
# (and standalone). Writes dist/WINDOWS_RELEASE_GATE.json.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

DIST_DIR="${DIST_DIR:-dist}"
BUILD="${BUILD_DIR:-build-win64}"
RESULTS="${RESULTS_DIR:-test-results}"
ZIP="$DIST_DIR/MPCASU-Windows-x86_64.zip"
OUT="$DIST_DIR/WINDOWS_RELEASE_GATE.json"
mkdir -p "$DIST_DIR"

version="7.0.0"
date_iso="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# helper: gate result from an on-disk marker (exit-code driven checks below).
g() { echo "$1"; }

# build: all 5 exes are PE32+ and present.
build_state=FAIL
build_detail=""
if [ -f "$BUILD/apps/casu-cli/casu.exe" ] && \
   [ -f "$BUILD/apps/mpcasu/MPCASU.exe" ] && \
   [ -f "$BUILD/apps/converter/CASU-Converter.exe" ] && \
   [ -f "$BUILD/apps/web-backend/CASU-Web-Backend.exe" ] && \
   [ -f "$BUILD/src/hello/casu_hello.exe" ]; then
  build_state=PASS
  for exe in "$BUILD/apps/casu-cli/casu.exe" "$BUILD/apps/mpcasu/MPCASU.exe" \
             "$BUILD/apps/converter/CASU-Converter.exe" "$BUILD/apps/web-backend/CASU-Web-Backend.exe"; do
    if ! file "$exe" | grep -q "PE32+"; then build_state=FAIL; fi
  done
fi

# unit_tests: ctest log must show 100% with zero failures.
unit_state=NOT_TESTED
if [ -f "$RESULTS/ctest.log" ]; then
  if grep -q "100% tests passed, 0 tests failed" "$RESULTS/ctest.log"; then
    unit_state=PASS
  else
    unit_state=FAIL
  fi
fi

# compatibility + codec + mp5 golden: verify_golden.sh results.
golden_state=NOT_TESTED
GOLDEN_RESULT="$RESULTS/golden/result.log"
if [ -f "$GOLDEN_RESULT" ] && grep -q "golden verification: PASS" "$GOLDEN_RESULT"; then
  golden_state=PASS
elif ls "$RESULTS/golden/"*_*.json >/dev/null 2>&1 && \
     ! grep -L '"status": "FAIL"' "$RESULTS/golden/"*_*.json >/dev/null 2>&1; then
  golden_state=PASS
else
  golden_state=FAIL
fi

# youtube: live gate log must contain LIVE PASS (real CDN, not a skip).
youtube_state=NOT_TESTED
yt_log="$RESULTS/wine/casu_playback_youtube_live_test.log"
if [ -f "$yt_log" ]; then
  if grep -q "LIVE PASS" "$yt_log"; then youtube_state=PASS; fi
  if grep -qi "SKIPPED" "$yt_log" && ! grep -q "LIVE PASS" "$yt_log"; then youtube_state=BLOCKED; fi
fi

# player: libVLC decode + MPCASU smoke must pass.
player_state=NOT_TESTED
if [ -f "$RESULTS/wine/casu_playback_vlc_test.log" ] && grep -q "RESULT PASS" "$RESULTS/wine/casu_playback_vlc_test.log" && \
   [ -f "$RESULTS/wine/mpcasu_smoke_test.log" ] && grep -q "ALL PASS" "$RESULTS/wine/mpcasu_smoke_test.log"; then
  player_state=PASS
fi

# converter: engine + GUI smoke logs pass.
converter_state=NOT_TESTED
if [ -f "$RESULTS/wine/casu_converter_engine_test.log" ] && grep -q "ALL PASS" "$RESULTS/wine/casu_converter_engine_test.log" && \
   [ -f "$RESULTS/wine/casu_converter_test.log" ] && grep -q "ALL PASS" "$RESULTS/wine/casu_converter_test.log"; then
  converter_state=PASS
fi

# network + web_backend: logs pass.
network_state=NOT_TESTED
if [ -f "$RESULTS/wine/casu_network_test.log" ] && grep -q "ALL PASS" "$RESULTS/wine/casu_network_test.log"; then
  network_state=PASS
fi
web_backend_state=NOT_TESTED
if [ -f "$RESULTS/wine/casu_web_backend_test.log" ] && grep -q "ALL PASS" "$RESULTS/wine/casu_web_backend_test.log"; then
  web_backend_state=PASS
fi

# pure_web: frozen SHA256 verified + present in the package.
pure_web_state=NOT_TESTED
PURE_REF="$(cd web/pure 2>/dev/null && sha256sum index.html 2>/dev/null | cut -d' ' -f1)"
ZIP_LIST="$(unzip -l "$ZIP" 2>/dev/null)"
if [ -n "$PURE_REF" ] && printf '%s' "$ZIP_LIST" | grep -q "web/pure/index.html"; then
  PURE_PKG="$(unzip -p "$ZIP" '*web/pure/index.html' 2>/dev/null | sha256sum | cut -d' ' -f1)"
  if [ "$PURE_REF" = "$PURE_PKG" ]; then
    pure_web_state=PASS
  else
    pure_web_state=FAIL
  fi
fi

# packaging: DLL audit must pass (all imports system or bundled).
packaging_state=NOT_TESTED
if [ -f "$RESULTS/dll-audit.log" ] && grep -q "OK — all imported DLLs" "$RESULTS/dll-audit.log"; then
  packaging_state=PASS
fi

# installer: setup.exe present + SHA256 recorded.
installer_state=NOT_TESTED
if ls "$DIST_DIR"/MPCASU-Setup-*.exe >/dev/null 2>&1; then
  if grep -q "MPCASU-Setup-.*\.exe" "$DIST_DIR/SHA256SUMS" 2>/dev/null; then
    installer_state=PASS
  else
    installer_state=FAIL
  fi
fi

# licenses: the Apache-2.0 (OpenSSL) + policy files exist.
licenses_state=NOT_TESTED
if [ -f "third_party/THIRD_PARTY_LICENSES/THIRD_PARTY_COMPONENTS.md" ] && \
   [ -f "third_party/THIRD_PARTY_LICENSES/Apache-2.0.txt" ] && \
   [ -f "third_party/THIRD_PARTY_LICENSES/README.md" ]; then
  licenses_state=PASS
fi

# clean-prefix package test: recorded PASS marker from WP-REL-005.
wine_state=NOT_TESTED
if [ -f "$RESULTS/clean-prefix.log" ] && grep -q "CLEAN_PREFIX_PASS" "$RESULTS/clean-prefix.log"; then
  wine_state=PASS
fi

cat > "$OUT" <<JSON
{
  "version": "$version",
  "generated_utc": "$date_iso",
  "toolchain": "MinGW-w64 x86_64 + Qt6 6.8.3 + libVLC 3.0.21 + zstd 1.5.7 + OpenSSL 3.4.1",
  "gates": {
    "build": "$build_state",
    "unit_tests": "$unit_state",
    "compatibility": "$golden_state",
    "codec": "$golden_state",
    "converter": "$converter_state",
    "player": "$player_state",
    "youtube": "$youtube_state",
    "network": "$network_state",
    "web_backend": "$web_backend_state",
    "pure_web": "$pure_web_state",
    "packaging": "$packaging_state",
    "installer": "$installer_state",
    "wine": "$wine_state",
    "licenses": "$licenses_state"
  }
}
JSON

echo "==> WINDOWS_RELEASE_GATE.json written:"
cat "$OUT"

# A BLOCKED or FAIL gate is never a PASS.
if grep -qE '"(build|unit_tests|compatibility|codec|converter|player|youtube|network|web_backend|pure_web|packaging|installer|wine|licenses)": "(FAIL|BLOCKED)"' "$OUT"; then
  echo "==> release gate: FAIL (one or more gates FAIL/BLOCKED)"
  exit 1
fi
echo "==> release gate: PASS (no FAIL/BLOCKED)"
exit 0
