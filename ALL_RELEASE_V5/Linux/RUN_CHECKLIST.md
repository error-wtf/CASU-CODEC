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
- Playlist-Queue: Playlist-Play ohne Ausklappen + Merge dedupliziert + gemischte
  Queue — durch Tests abgedeckt (20 Playlist-Tests).
- MIME: `.casu`-Datei im Dateimanager → MPCASU (nach DEB-Installation).
- Keine falschen PASS: Syntax-Check ≠ Tests grün ≠ UI-Verhalten korrekt.
- YouTube: echter Stream via yt-dlp → Loopback → libVLC (nicht nur Mock).

## Fehlerbehandlung
- Ursache verstehen → lösen ODER als BLOCKED dokumentieren (BLOCKERS.md im
  win-release/roadmap/ oder NOTIZEN an Nutzer). Nie still Feature weglassen.

## Häufige Stolperfallen
- PlaylistModel ist flach — Gruppen nur im UI.
- Durchspielen ohne Ausklappen: Einträge aus Datei laden (nicht UI-Kinder).
- Visualizer: Repaint-Schleife nur bei sichtbarem Fenster (sonst CPU-Pegel).
- Wayland vs X11: Launcher wählt je Session.
- `build_debs.sh` leert `dist/` — PURE-WEB-ZIP danach wiederherstellen.