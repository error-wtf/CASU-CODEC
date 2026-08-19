#!/usr/bin/env bash
# test-guard.sh — führt nach Feature-Änderungen die Regressionstests aus und
# stellt bei Fehlern das letzte funktionierende Backup wieder her.
#
# So schützen wir funktionierenden Code: Jede Änderung wird erst durch die
# Tests bestätigt; schlägt etwas fehl, wird sofort auf das letzte grüne Backup
# zurückgerollt (statt ein kaputtes Release zu bauen).
#
# Nutzung:
#   ./test-guard.sh run        # Tests ausführen; bei Fehler automatisch restore
#   ./test-guard.sh run --no-restore   # nur testen, kein Auto-Rollback
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
BACKUP_ROOT="${BACKUP_ROOT:-/tmp/opencode/backups}"
ROLLBACK=1
[ "${2:-}" = "--no-restore" ] && ROLLBACK=0

# Zuletzt erstelltes Backup = Wiederherstellungspunkt.
latest_backup() {
  local latest=""
  for d in "$BACKUP_ROOT"/*; do
    [ -d "$d" ] || continue
    [ -z "$latest" ] && latest="$d" && continue
    [ "$d" -nt "$latest" ] && latest="$d"
  done
  [ -n "$latest" ] && basename "$latest" || echo ""
}

echo "==> test-guard: Start ($(date -u +%Y-%m-%dT%H:%M:%SZ))"

fail=0
run_suite() {
  cd "$REPO"
  echo "--- [Linux] Syntax-Checks ---"
  python3 -m py_compile mpcasu_qt/main_window.py casu/playlist.py || fail=1

  echo "--- [Linux] Playlist-Tests ---"
  timeout 120 pytest tests/test_playlist.py -q >/dev/null 2>&1 || fail=1
  echo "    test_playlist: $([ $fail -eq 0 ] && echo PASS || echo FAIL)"

  echo "--- [Linux] Player-UI-Tests (xvfb) ---"
  timeout 180 xvfb-run -a pytest tests/test_player_ui.py -q >/dev/null 2>&1 || fail=1
  echo "    test_player_ui: $([ $fail -eq 0 ] && echo PASS || echo FAIL)"

  echo "--- [Windows] Build (MPCASU) ---"
  cd "$REPO/win-release"
  cmake --build build-win64 --target casu_mpcasu >/tmp/opencode/test-guard-build.log 2>&1 || fail=1
  echo "    build: $([ $fail -eq 0 ] && echo PASS || echo FAIL)"
  cd "$REPO"
}

run_suite

if [ "$fail" -eq 0 ]; then
  echo "==> test-guard: ALLE TESTS BESTANDEN (funktionierend)."
  exit 0
fi

echo "==> test-guard: TESTS FEHLGESCHLAGEN."
if [ "$ROLLBACK" -eq 1 ]; then
  local_backup="$(latest_backup)"
  echo "    -> Rollback auf letztes Backup: $local_backup"
  "$HERE/safe-guard.sh" restore "$local_backup"
  echo "    -> Wiederhergestellt. Tests erneut..."
  fail=0
  run_suite
  if [ "$fail" -eq 0 ]; then
    echo "==> Nach Rollback: ALLE TESTS BESTANDEN."
    exit 0
  fi
fi
echo "==> test-guard: FEHLGESCHLAGEN (auch nach Rollback). Bitte manuell prüfen."
exit 1