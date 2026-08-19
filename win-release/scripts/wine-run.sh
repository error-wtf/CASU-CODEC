#!/usr/bin/env bash
# wine-run.sh — shared Wine test harness (WP-DEV-000).
#   wine-run.sh <exe> [args...]
# Runs a cross-compiled Windows exe in the isolated prefix .wine-test under
# xvfb, captures stdout/stderr to test-results/wine/, and returns the exe exit
# code. Safe to call from ctest (CTest/ctest).

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

export WINEPREFIX="${WINEPREFIX:-$PWD/.wine-test}"
export WINEDEBUG="${WINEDEBUG:--all}"   # quiet; logs captured explicitly below

mkdir -p .wine-test test-results/wine

# Lazy init of the isolated prefix (once; ignores first-run noise).
if [[ ! -f "$WINEPREFIX/system.reg" ]]; then
    wineboot -u >/dev/null 2>&1 || true
fi

EXE="${1:?usage: wine-run.sh <exe> [args...]}"
shift

mkdir -p test-results/wine
BASE="$(basename "$EXE" .exe)"
LOG="test-results/wine/${BASE}.log"

# xvfb-run isolates the GUI platform; the exe itself is invoked by wine.
set +e
xvfb-run -a wine "$EXE" "$@" > "$LOG" 2>&1
RC=$?
set -e

echo "== wine-run.sh: $EXE -> exit $RC (log: $LOG) =="
exit $RC
