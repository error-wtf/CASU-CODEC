# SAFE-GUARD.md — Absicherung: Backups + Regressionstests

Zweck: **Funktionierenden Code niemals zerstören.** Vor jeder Feature-Änderung
und nach jeder Änderung läuft ein fester Ablauf aus Backup + Tests. Bei einem
Fehler wird sofort auf das letzte funktionierende Backup zurückgerollt.

Pfade relativ zu `win-release/`. Skripte: `win-release/scripts/`.

## 1. Der Absicherungs-Loop (IMMER bei Feature-Arbeit)

```bash
# 1) Backup des aktuellen funktionierenden Zustands (mit sprechendem Tag)
./win-release/scripts/safe-guard.sh backup <tag>     # z.B. v3-before-xyz

# 2) Feature ändern ...

# 3) Regressionstests: bei Fehler automatisch Rollback auf letztes Backup
./win-release/scripts/test-guard.sh run               # oder --no-restore

# 4) Bestätigen: Quelldateien == letztes Backup (wenn unverändert)
./win-release/scripts/safe-guard.sh verify
```

## 2. safe-guard.sh — Backup + Wiederherstellung

- `safe-guard.sh backup <tag>`   — sichert alle zu schützenden Dateien
  (Linux: `mpcasu_qt/main_window.py`, `casu/playlist.py`, `packaging/build_debs.sh`;
   Windows: `win-release/apps/mpcasu/{main_window,playlist,main_window.hpp}`,
  `win-release/scripts/setup.nsi`).
- `safe-guard.sh list`           — zeigt alle Backups.
- `safe-guard.sh restore <tag>`  — stellt die Dateien eines Backups wieder her.
- `safe-guard.sh verify`         — prüft, ob die Quelldateien mit dem LETZTEN
  Backup übereinstimmen (zeigt ungewollte Änderungen).

Ablage: `$BACKUP_ROOT/<tag>/<pfad-mit-underscores>.bak` (Default `/tmp/opencode/backups`).

## 3. test-guard.sh — Regressionstests + Auto-Rollback

- `test-guard.sh run`            — führt aus: Linux Syntax-Checks, Playlist-Tests,
  Player-UI-Tests (xvfb), Windows-Build. Bei Fehler: Restore auf letztes Backup
  + erneuter Testlauf.
- `test-guard.sh run --no-restore` — nur testen, kein Auto-Rollback.

## 4. Wiederherstellungspunkte (Stand 2026-08-19)
- `v3-before-playlist-feature`   — Zustand vor der Playlist-Queue-Arbeit.
- `v3-after-linux-playlist-fixes`— funktionierender Zwischenstand nach den
  Linux-Playlist-Fixes (`_play_playlist_full` + `_current_playlist_context`),
  Tests grün.

## 5. Was bei der Playlist-Queue-Arbeit gilt (WICHTIG, aus Analyse)
- Linux-Model (`casu/playlist.py PlaylistModel`) ist FLACH (Liste von Path/str);
  Playlist-**Gruppen** sind reine UI-Konstrukte im `PlaylistPane` (QTreeWidget).
- `load_playlist` addet NUR die Einträge (`loaded.items`), NICHT die Playlist-
  Datei → keine echte Gruppe entsteht außer bei Drag&Drop der .m3u selbst.
- `_current_playlist_context` wurde so geändert, dass das Durchspielen einer
  Playlist **ohne Ausklappen** funktioniert (Einträge aus Datei laden, nicht aus
  UI-Kindern). Siehe `WINDOWS_INSTALL_AND_CODEC.md` + diese Analyse.
- Nach jedem Feature-Schritt: `test-guard.sh run`; nie ein Release bauen, solange
  die Tests nicht grün sind.