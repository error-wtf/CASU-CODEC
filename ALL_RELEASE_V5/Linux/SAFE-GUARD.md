# SAFE-GUARD — Absicherung: Backups + Regressionstests (Linux)

Zweck: **Funktionierenden Code niemals zerstören.** Gleicher Loop wie beim
Windows-Port; Skripte liegen in `win-release/scripts/` und decken beide Seiten ab.

## 1. Der Absicherungs-Loop (IMMER bei Feature-Arbeit)

```bash
./win-release/scripts/safe-guard.sh backup <tag>   # z.B. v5-before-xyz
# Feature ändern ...
./win-release/scripts/test-guard.sh run            # Linux-Tests + Windows-Build; Auto-Rollback bei Fehler
./win-release/scripts/safe-guard.sh verify
```

## 2. safe-guard.sh — was geschützt wird (Linux-Teil)

- `mpcasu_qt/main_window.py`, `casu/playlist.py`, `packaging/build_debs.sh`
  (plus die Windows-Dateien). Backup-Root `/tmp/opencode/backups`.

## 3. test-guard.sh — Linux-Umfang

- Python-Syntax-Checks (`python3 -m py_compile` über alle Referenzmodule).
- `tests/test_playlist.py` — 20 Tests (Playlist-Formate, Merge, Crash-Sicherheit,
  Play-Queue-Roundtrip).
- `tests/test_player_ui.py` — 9 UI-Tests unter xvfb.
- Danach Windows-Build (Cross-Compile) — beide Seiten müssen grün sein.

## 4. Linux-spezifische Regeln

- **Playlist-Modell ist FLACH** (`casu/playlist.py PlaylistModel` = Liste von
  Path/str); Playlist-Gruppen sind reine UI-Konstrukte im PlaylistPane
  (QTreeWidget). Beim Portieren/Merge nie Gruppen im Model erzeugen.
- `_current_playlist_context`: Durchspielen einer Playlist ohne Ausklappen —
  Einträge aus der Datei laden, nicht aus UI-Kindern.
- MIME: `.casu`-Assoziation kommt aus `packaging/casu-codec-mime.xml`;
  Änderungen → DEB neu bauen + postinst-Pfad testen.
- `build_debs.sh` leert `dist/` → PURE-WEB-ZIP danach ggf. wiederherstellen
  (`git checkout -- dist/MPCASU-PURE-WEB-3.0.0.zip`), `dist/SHA256SUMS` neu.

## 5. Bekannte Backups (Stand 2026-08-19)
`v3-before-playlist-feature`, `v3-after-linux-playlist-fixes`,
`v3-linux-playlist-merge-done`, `v3-playlist-feature-complete`.