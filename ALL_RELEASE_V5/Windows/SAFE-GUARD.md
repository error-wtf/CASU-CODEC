# SAFE-GUARD — Absicherung: Backups + Regressionstests (Windows)

Zweck: **Funktionierenden Code niemals zerstören.** Vor jeder Feature-Änderung
und nach jeder Änderung läuft ein fester Ablauf aus Backup + Tests.

Skripte liegen in `win-release/scripts/`; Backup-Root `/tmp/opencode/backups`.

## 1. Der Absicherungs-Loop (IMMER bei Feature-Arbeit)

```bash
# 1) Backup des aktuellen funktionierenden Zustands
./win-release/scripts/safe-guard.sh backup <tag>     # z.B. v5-before-xyz

# 2) Feature ändern ...

# 3) Regressionstests (bei Fehler Auto-Rollback auf letztes Backup)
./win-release/scripts/test-guard.sh run               # oder --no-restore

# 4) Bestätigen: Quelldateien == letztes Backup (wenn unverändert)
./win-release/scripts/safe-guard.sh verify
```

## 2. safe-guard.sh — Backup + Wiederherstellung

- `backup <tag>` — sichert geschützte Dateien (Linux-Player + Packaging,
  Windows-Player + setup.nsi).
- `list` / `restore <tag>` / `verify` — Liste, Wiederherstellen, Prüfen.

Bekannte Backups (Stand 2026-08-19): `v3-before-playlist-feature`,
`v3-after-linux-playlist-fixes`, `v3-linux-playlist-merge-done`,
`v3-playlist-feature-complete`.

## 3. test-guard.sh — Regressionstests + Auto-Rollback

`run` = Linux Syntax-Checks + Playlist-Tests + Player-UI-Tests (xvfb) +
Windows-Build; bei Fehler Restore + erneuter Lauf. `run --no-restore` = nur testen.

## 4. Windows-spezifische Gates (nie überspringen)

- **YouTube/Netzwerk**: echtes YouTube/CDN unter Wine (nicht nur Mock).
- **GUI/Playback**: echter Windows-Build unter Wine + Screenshot-Vergleich.
- **Codec/Converter**: Golden-Vergleich (Hashes/JSON) Linux↔Wine.
- **Clean-Prefix**: gepacktes Release in NEUEM WINEPREFIX; nur Paket-Inhalt.
- **Keine falschen PASS**: "kompiliert" ≠ "Unit grün" ≠ "funktioniert".

## 5. Stolperfallen (aus der Windows-Port-Analyse)

- libVLC-State 6/7 + zero-time-EOF (mpcasu_backend.py:600-627).
- YouTube-Lifecycle: stop old → start proxy → open; nie Proxy vor open killen.
- VideoSurface: keine Qt-Overlays aufs native Video; HWND-Lifetime; qwindows.dll.
- Threading: Qt-GUI nur GUI-Thread; Audio: WASAPI/Qt (kein PulseAudio).
- Wine ≠ Windows: Wine-Workarounds nicht als universelle Lösung coden.

## 6. Reproduzierbarer Release-Build (Windows)

```bash
cd win-release
setsid nohup ./scripts/build-windows-release.sh > test-results/release-build.log 2>&1 < /dev/null &
# makensis-Fix (Skript-Bug): dist/_stage manuell befüllen, dann makensis
# Abschluss: sha256sum + ./scripts/release_gate.sh (14 Gates, WINDOWS_RELEASE_GATE.json)
```