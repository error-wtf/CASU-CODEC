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
- **Nicht-destruktive Gruppen-Queue (v3.0.0-Nachfolger):** Playlist bleibt im
  Queue sichtbar (Gruppenzeile, nie aufgelöst); abgespielt wird die logische
  Sequenz der flachen Einträge (`_play_seq`, gecacht; `invalidate_seq()`
  invalidiert bei jeder Queue-Änderung). Gruppen + Mehrfachauswahl verschiebbar
  (↑/↓, Kontextmenü), Einträge ein- ("rein")/aussortierbar ("raus"), Batch-Dedup.
  Das alte `_current_playlist_context`-Konzept ist ENTFERNT — Playlist-Play
  läuft über die logische Sequenz, nicht über separate Kontext-Ladung.
- Web-Player (`web/` + `pure-web-release/`): flaches `state.items`-Modell mit
  `item.playlist`-Attribut (Gruppen = UI/Attribut, EPG/IPTV-Views iterieren
  flach); Gruppen bleiben nie aufgelöst; `moveRowSegment` mit Bounds-Check VOR
  dem Splice (nie Item-Verlust).
- MIME: `.casu`-Assoziation kommt aus `packaging/casu-codec-mime.xml`;
  Änderungen → DEB neu bauen + postinst-Pfad testen.
- `build_debs.sh` leert `dist/` → PURE-WEB-ZIP danach ggf. wiederherstellen
  (`git checkout -- dist/MPCASU-PURE-WEB-3.0.0.zip`), `dist/SHA256SUMS` neu.

## 5. Bekannte Backups (Stand 2026-08-19)
`v3-before-playlist-feature`, `v3-after-linux-playlist-fixes`,
`v3-linux-playlist-merge-done`, `v3-playlist-feature-complete`.

## 6. Launcher-/Sandbox-Fixes (2026-08-19, in v3.0.0-DEBs enthalten)
- **Stray-`mpcasu_qt`-Shadowing:** `/usr/bin/mpcasu` macht jetzt `cd /`, damit
  ein `./mpcasu_qt` im aktuellen Verzeichnis NIEMALS die installierte Version
  (/usr/share/casu-codec) überschattet. Vorher wurde beim Start aus Repo-
  Verzeichnissen eine alte Kopie ohne Playlist-Fixes geladen → "broken".
- **QtWebEngine-Sandbox als root/Container:** `QTWEBENGINE_DISABLE_SANDBOX=1`
  wenn `id -u = 0` (Chromium-Zygote crashte die GUI beim Start sonst still).
- **Weitere alte mpcasu_qt-Kopien** (Lino-Codec, Dokumente/Codec-Casu,
  Lino-Codec-work-recovered, Lino-Codec-VOLLBACKUP-*) wurden auf den Stand der
  reparierten Referenz ersetzt (Backups: `/tmp/opencode/alt-main-windows/`).
- Bei künftigen Fixes IMMER: DEBs neu bauen, `mpcasu`-Skript verifizieren
  (`grep -c 'cd /' /usr/bin/mpcasu`), Test als root (`mpcasu` startet ohne
  Zygote-Crash), und alle externen mpcasu_qt-Kopien prüfen.