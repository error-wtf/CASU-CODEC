# RUN_CHECKLIST — fehlerfreier Ablauf (Linux)

Ein Feature nach dem anderen, immer derselbe Loop. "VERIFIED" nur mit Nachweis.

## Pro Sitzung — Start (immer)
1. `cd /home/error/Codec-Casu`
2. `git status --short` → nur erwartete Änderungen.
3. `PORT_STATUS.md` (Linux) lesen → aktueller Schritt.
4. `git rev-parse HEAD` protokollieren.

## Pro Feature — der Loop
1. **ANALYSIS**: Referenz lesen (bei Fragen: `REFERENCE_LOOKUP` im
   `win-release/`-Baum, Git-Historie).
2. **BACKUP**: `./win-release/scripts/safe-guard.sh backup <tag>`.
3. **IMPLEMENTIEREN**: in `mpcasu_qt/`, `casu/`, `packaging/` (Nutzer-Referenz —
   Änderungen erlaubt, Nutzer hat sie freigegeben).
4. **TESTS**:
   `pytest tests/test_playlist.py tests/test_player_ui.py -q` (xvfb für UI)
   → alles grün.
5. **WINDOWS-PARITÄT**: `./win-release/scripts/test-guard.sh run` → auch der
   Windows-Build muss grün bleiben (gemeinsame Semantik).
6. **VERIFIED** NUR wenn alle Gates grün → `PORT_STATUS.md` + `FEATURE_MATRIX.md`
   aktualisieren.

## Harte Gates (nie überspringen)
- Playlist-Queue (nicht-destruktiv): Playlist-Gruppen bleiben beim Spielen
  sichtbar (kein Auflösen); logische Sequenz spielt Gruppen + lose
  Dateien/URLs gemischt durch; Gruppen + Mehrfachauswahlen (Strg/Shift)
  verschiebbar; Einträge ein- ("Save selection…"/"Move to playlist…") und
  aussortierbar ("Remove from playlist"); Batch-Dedup (Playlist + eigene
  Dateien → kein Doppelt-Laden) — durch `tests/test_queue_playback_behavior.py`
  + `tests/test_playlist.py` abgedeckt (432 passed, 12 skipped, Stand 2026-08-20).
- MIME: `.casu`-Datei im Dateimanager → MPCASU (nach DEB-Installation).
- Keine falschen PASS: Syntax-Check ≠ Tests grün ≠ UI-Verhalten korrekt.
- YouTube: echter Stream via yt-dlp → Loopback → libVLC (nicht nur Mock).
- Web-Player (web-casu + Pure Web): `node --check web/app.js pure-web-release/app.js`,
  Node-Harness ALL PASS (`/tmp/opencode/webapp_queue_test.js` 12 Checks,
  `/tmp/opencode/pureweb_queue_test.js` 17 Checks), `python3 tools/smoke_web_playlist.py`
  mehrfach grün (Gruppen-Tools, Block-Move, Mehrfachauswahl, rein/raus,
  Save-selection).

## Fehlerbehandlung
- Ursache verstehen → lösen ODER als BLOCKED dokumentieren (BLOCKERS.md im
  win-release/roadmap/ oder NOTIZEN an Nutzer). Nie still Feature weglassen.

## Häufige Stolperfallen
- **Gruppen bleiben sichtbar:** Playlist-Zeilen werden beim Spielen NIE
  aufgelöst — Wiedergabe läuft über die logische Sequenz (`_play_seq`), nicht
  über Modell-Änderungen. Jede Queue-Mutation muss die Sequenz invalidieren
  (`_invalidate_play_seq`), sonst spielt Next/Previous eine veraltete Liste.
- PlaylistModel ist flach — Gruppen nur im UI.
- Durchspielen ohne Ausklappen: Einträge aus Datei laden (nicht UI-Kinder).
- Visualizer: Repaint-Schleife nur bei sichtbarem Fenster (sonst CPU-Pegel).
- Wayland vs X11: Launcher wählt je Session.
- `build_debs.sh` leert `dist/` — PURE-WEB-ZIP danach wiederherstellen.
- **Stray-Kopien:** `mpcasu` lädt die INSTALLIERTE Version (cd / im Skript);
  vorher konnte ein `./mpcasu_qt` im cwd eine alte Kopie laden → nach jedem
  Release alle externen mpcasu_qt-Kopien prüfen/ersetzen.
- **Root/Container:** QtWebEngine braucht `QTWEBENGINE_DISABLE_SANDBOX=1`
  (im Launcher, wenn uid=0); ohne das crasht die GUI still beim Start.