#!/usr/bin/env bash
# safe-guard.sh — Backup- und Wiederherstellungs-System für den CASU/MPCASU-Port.
# Schützt funktionierenden Code, bevor Features geändert werden.
#
# Nutzung:
#   ./safe-guard.sh backup   [tag]   # sichere alle geänderten Dateien (mit optionalem Tag)
#   ./safe-guard.sh list             # zeige alle Backups
#   ./safe-guard.sh restore <tag>    # stelle die Dateien eines Backups wieder her
#   ./safe-guard.sh verify           # prüfe, dass die Quelldateien mit dem letzten Backup übereinstimmen
#
# Backup-Struktur: /tmp/opencode/backups/<tag>/<rel-pfad>.bak
set -uo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/tmp/opencode/backups}"
# scripts/ liegt unter win-release/scripts/; das Repo-Root ist zwei Ebenen höher.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Alle Dateien, die wir beim Feature-Arbeiten ändern (Linux + Windows).
FILES=(
  "mpcasu_qt/main_window.py"
  "casu/playlist.py"
  "win-release/apps/mpcasu/main_window.cpp"
  "win-release/apps/mpcasu/playlist.cpp"
  "win-release/apps/mpcasu/playlist.hpp"
  "win-release/apps/mpcasu/main_window.hpp"
  "win-release/scripts/setup.nsi"
  "packaging/build_debs.sh"
)

default_tag="snapshot-$(date +%Y%m%d-%H%M%S)"

cmd="${1:-backup}"
tag="${2:-$default_tag}"

backup() {
  local dir="$BACKUP_ROOT/$tag"
  mkdir -p "$dir"
  echo "==> Backup nach: $dir"
  for f in "${FILES[@]}"; do
    if [ -f "$REPO/$f" ]; then
      local rel="${f//\//_}"
      cp -v "$REPO/$f" "$dir/$rel.bak" >/dev/null && echo "    OK: $f"
    else
      echo "    (übersprungen, fehlt): $f"
    fi
  done
  echo "==> Backup fertig: $tag"
}

list() {
  echo "==> Verfügbare Backups:"
  for d in "$BACKUP_ROOT"/snapshot-* "$BACKUP_ROOT"/*; do
    [ -d "$d" ] && echo "  $(basename "$d") — $(ls -1 "$d" | wc -l) Dateien"
  done
}

restore() {
  local dir="$BACKUP_ROOT/$tag"
  if [ ! -d "$dir" ]; then
    echo "FEHLER: Backup '$tag' existiert nicht." >&2
    exit 1
  fi
  echo "==> Wiederherstellen von: $tag"
  for f in "${FILES[@]}"; do
    local rel="${f//\//_}"
    if [ -f "$dir/$rel.bak" ]; then
      cp -v "$dir/$rel.bak" "$REPO/$f" && echo "    wiederhergestellt: $f"
    fi
  done
  echo "==> Wiederherstellung fertig."
}

verify() {
  echo "==> Verifiziere: Quelldateien == letztes Backup"
  # Finde das zuletzt modifizierte Backup-Verzeichnis (nach mtime).
  local latest=""
  for d in "$BACKUP_ROOT"/*; do
    [ -d "$d" ] || continue
    [ -z "$latest" ] && latest="$d" && continue
    [ "$d" -nt "$latest" ] && latest="$d"
  done
  if [ -z "$latest" ]; then echo "   (kein Backup vorhanden)"; return 0; fi
  echo "   Letztes Backup: $(basename "$latest")"
  local dirty=0
  for f in "${FILES[@]}"; do
    local rel="${f//\//_}"
    if [ -f "$REPO/$f" ] && [ -f "$latest/$rel.bak" ]; then
      if ! diff -q "$REPO/$f" "$latest/$rel.bak" >/dev/null 2>&1; then
        echo "   GEÄNDERT seit Backup: $f"
        dirty=1
      fi
    fi
  done
  [ "$dirty" -eq 0 ] && echo "   OK: keine Abweichungen zum letzten Backup."
}

case "$cmd" in
  backup)  backup ;;
  list)    list ;;
  restore) restore "$tag" ;;
  verify)  verify ;;
  *) echo "Unbekannter Befehl: $cmd (backup|list|restore|verify)" >&2; exit 2 ;;
esac