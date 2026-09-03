#!/usr/bin/env bash
# build-windows-release.sh — reproducible Windows-port pipeline.
#   configure → build → unit (wine) → stage → package (CPack zip) → sha256 → gate
# Runs from win-release/. Writes into build-win64/, dist/ and test-results/.
# Reference tree stays read-only; only win-release/ is touched.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

BUILD_DIR="${BUILD_DIR:-build-win64}"
DIST_DIR="${DIST_DIR:-dist}"
RESULTS_DIR="test-results"
TOOLCHAIN="cmake/mingw64-toolchain.cmake"
SKIP_WINE="${SKIP_WINE:-0}"

# Absolute paths: the packaging steps run in subshells that change directory.
BUILD_DIR="$(realpath "$BUILD_DIR")"
DIST_DIR="$(realpath "$DIST_DIR")"
RESULTS_DIR="$(realpath "$RESULTS_DIR")"

mkdir -p "$RESULTS_DIR" "$DIST_DIR"

echo "==> [1/8] configure"
cmake -S . -B "$BUILD_DIR" -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="$TOOLCHAIN" \
    -DCMAKE_BUILD_TYPE=Release

echo "==> [2/8] build"
cmake --build "$BUILD_DIR"

echo "==> [3/8] unit (cross-compiled binaries under Wine)"
if [[ "$SKIP_WINE" == "0" ]]; then
    export WINEPREFIX="${WINEPREFIX:-$PWD/.wine-test}"
    if [[ ! -d "$WINEPREFIX/drive_c" ]]; then
        echo "    initializing wine prefix $WINEPREFIX"
        wineboot -u >/dev/null 2>&1 || true
    fi
    ctest --test-dir "$BUILD_DIR" --output-on-failure > "$RESULTS_DIR/ctest.log" 2>&1 || {
        echo "    ctest FAILED — see $RESULTS_DIR/ctest.log"; tail -40 "$RESULTS_DIR/ctest.log"; exit 1; }
else
    echo "    skipped (SKIP_WINE=1)"
fi

echo "==> [4/8] wine app smoke"
if [[ "$SKIP_WINE" == "0" ]]; then
    xvfb-run -a wine "$BUILD_DIR/src/hello/casu_hello.exe" > "$RESULTS_DIR/hello-wine.log" 2>&1
    xvfb-run -a wine "$BUILD_DIR/tests/casu_core_test.exe" > "$RESULTS_DIR/casu_core_test-wine.log" 2>&1
fi

echo "==> [5/8] stage (CPack)"
rm -rf "$DIST_DIR/_stage"
cpack --config "$BUILD_DIR/CPackConfig.cmake" -B "$DIST_DIR/_stage" > "$RESULTS_DIR/cpack.log" 2>&1
# Move the single self-contained zip into dist/ for the final artifact.
if [[ -f "$DIST_DIR/_stage/MPCASU-Windows-x86_64.zip" ]]; then
    mv -f "$DIST_DIR/_stage/MPCASU-Windows-x86_64.zip" "$DIST_DIR/"
fi

echo "==> [6/8] sha256"
find "$DIST_DIR" -maxdepth 1 -name 'MPCASU-Windows-x86_64.zip' -exec sha256sum {} + > "$DIST_DIR/SHA256SUMS"

echo "==> [7/8] DLL audit"
./scripts/dll-audit.sh \
    "$BUILD_DIR/apps/casu-cli/casu.exe" \
    "$BUILD_DIR/apps/mpcasu/MPCASU.exe" \
    "$BUILD_DIR/apps/converter/CASU-Converter.exe" \
    "$BUILD_DIR/apps/web-backend/CASU-Web-Backend.exe" \
    "$BUILD_DIR/src/hello/casu_hello.exe" > "$RESULTS_DIR/dll-audit.log" 2>&1
echo "    DLL audit: $(grep -c 'OK ' "$RESULTS_DIR/dll-audit.log") OK"

echo "==> [7b/8] setup.exe installer"
# Extract the staged package tree (CPack leaves only the zip) and compile the
# NSIS installer into dist/. Requires makensis (NSIS) on the build host.
if command -v makensis >/dev/null 2>&1; then
    rm -rf "$DIST_DIR/_stage/MPCASU-Windows-x86_64"
    (cd "$DIST_DIR/_stage" && unzip -oq "$DIST_DIR/MPCASU-Windows-x86_64.zip")
    if makensis scripts/setup.nsi > "$RESULTS_DIR/setup-nsis.log" 2>&1; then
        installer="dist/MPCASU-Setup-7.0.0.exe"
        if [[ "$DIST_DIR" != "$(realpath dist)" && -f "$installer" ]]; then
            cp -f "$installer" "$DIST_DIR/"
        fi
        echo "    OK: $(ls -1 "$DIST_DIR"/MPCASU-Setup-*.exe)"
    else
        echo "    makensis failed — see $RESULTS_DIR/setup-nsis.log"; tail -10 "$RESULTS_DIR/setup-nsis.log"; exit 1
    fi
else
    echo "    makensis not found — skipping setup.exe (install NSIS: apt install nsis)"
fi

echo "==> [7c/8] sha256 (zip + setup)"
find "$DIST_DIR" -maxdepth 1 \( -name 'MPCASU-Windows-x86_64.zip' -o -name 'MPCASU-Setup-*.exe' \) \
    -exec sha256sum {} + | sort > "$DIST_DIR/SHA256SUMS"

echo "==> [8/8] gate"
if [[ "$SKIP_WINE" == "0" ]]; then
    ./tests/golden/verify_golden.sh > "$RESULTS_DIR/golden/result.log" 2>&1 || {
        echo "    golden FAILED"; tail -10 "$RESULTS_DIR/golden/result.log"; exit 1; }
    echo "    golden: $(grep -c 'PASS' "$RESULTS_DIR/golden/result.log") PASS"
fi
./scripts/release_gate.sh
