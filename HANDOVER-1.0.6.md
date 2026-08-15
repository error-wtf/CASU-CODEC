HANDOVER 1.0.6 (Session 10, 2026-08-15) — CASU/MPCASU
=========================================================
Diese Datei ist die neue, selbsttragende Arbeitsgrundlage.
Ältere Doku: /home/error/HANDOVER-KOMPLETT.md (Sessions 1–9),
/home/error/handover-new/handover.txt + handover-session5.txt.

!!! SICHERHEIT !!!
- GitHub-Token liegt NUR in /home/error/gittoken.env (NIE committen, NIE in
  Doku/Handover/Repo, NIE in Befehlen die persistiert werden).
- KEIN Push ohne expliziten Nutzer-Auftrag. Aktueller Stand: LOCAL ahead.
- Regeln: Backup vor Änderung; kein rm -rf auf Repos/Daten; kein Force-Push;
  keine Secrets; dopo-DEB-Rebuild: cp -a dist backups/...

GIT-STAND
- Repo: /home/error/Codec-Casu (Branch main)
- LOCAL HEAD: 1df4e24  (Release 1.0.6, UNPUSHED)
- REMOTE HEAD: 88300b2 (Release 1.0.5) — Push + GitHub-Release v1.0.6
  stehen AUS und erfolgen nur auf expliziten Auftrag mit frischem Token.
- Remote ist PUBLIC; Branch backup/remote-main-pre-session5 = alter
  Remote-Stand vor Session 6 (Sicherheitsskopie).

INSTALLATION (diese Maschine)
- Pakete 1.0.6 installiert: casu-codec, casu-converter, mpcasu, web-casu
  (dpkg -V sauber). /usr/bin/mpcasu startet wieder (QtNetwork-Fix).
- spotDL-venv: /opt/casu-spotdl (optional, Spotify-Provider).
- Webplayer läuft als User-Prozess auf Port 8765 (web-casu).

WAS SEIT 1.0.2 PASSIERT IST (kompakt)
1.0.3: Stabilization pass — CASU-Routing magic-byte-first (CASUNAT2 native /
  CASUNAT1 compatibility / MP5 enhanced / Legacy-JSON explizit), Sidecar-
  Framing entfernt, Spotify→spotDL-Provider + ehrlicher YouTube-Handoff,
  Qt-Playlists/Fullscreen/Escape repariert, Acceptance-Layer
  tools/acceptance_qt.py + tools/acceptance_web.py, GitHub-Release v1.0.3.
1.0.4: UX-Parität nach Review — Transport-Hierarchie (⋯-Panel), Video-
  Fullscreen mit Auto-Hide-Overlay, Responsiv (Rail <1200px, Playlist-Drawer
  <1000px, ☰/☷), Drop-Overlay, Queue-Produktreife (View-Filter, rekursive
  Suche, persistentes Rename, echte Thumbnails async, EXTINF-Namen in Queue
  + Caption), Options mit Provider-Statusseite + Record-Optionen (Ordner,
  Split nach Zeit, Format), LIVE-GUIDE-Card, Release v1.0.5? NEIN: v1.0.4.
1.0.5: Single-Instance-Guard (QLocalServer), Geometrie-Clamp show/move/resize
  (Click-Region-Offset behoben), Live-Stream-FFT-Visualizer (ffmpeg-Tap,
  echte Messdaten, Web-Parität), A–B/Snapshot/Record sichtbar (Web-Dichte).
  Release v1.0.5 gepusht (88300b2).
1.0.6 (LOCAL, ungepusht): Lizenz 5a = ehrliche Attribution (VLC/libVLC
  LGPL/GPL, Webamp MIT, yt-dlp Unlicense, spotDL MIT — Ideen/Vorlagen, eigener
  Code); mpcasu-Startfix (PySide6.QtNetwork optional + DEB-Dep
  python3-pyside6.qtnetwork); spotdl-Aufruf fix (`save --save-file`,
  List-Parser für .spotdl-Output).

OFFENE FEHLER / LIMITATIONS (ehrlich)
1. SPOTIFY AUF DIESER MASCHINE NETZSEITIG BLOCKIERT: api.spotify.com liefert
   410/404 (Proxy/Filter); spotdl hängt teils bis Timeout. Code-Fallbacks:
   ehrliche Fehlermeldung + „Find on YouTube"-Handoff (oEmbed-Titel, ebenfalls
   blockiert → YouTube-Suche bleibt als eigener Provider nutzbar).
   => Spotify-Flows MÜSSEN auf einem Netz ohne Spotify-Block getestet werden.
2. Gates 4–6 bleiben PARTIAL (historische Tk-Matrizen nicht voll auf Qt
   wiederholt; acceptance_qt/web sind die neue Evidenz).
3. Tk-Player (mpcasu_player.py) = nur noch Referenz; offiziell ist Qt.
4. CASUNAT1/legacy-Start dauert Sekunden (Extraktion+libVLC); unter Xvfb-Last
   Timing-Flakes in acceptance_qt (einzeln OK).

TESTBEFEHLE
- /usr/bin/python3 -m pytest -q -m 'not media'          # 225 passed
- tools/acceptance_qt.py   (DISPLAY=:95, installiert)   # 16 Checks
- tools/acceptance_web.py  (miniconda-playwright)       # 16/16
- xvfb-run -a python3 -m pytest tests/test_player_ui.py tests/test_converter_ui.py -q
- tools/smoke_owner_casu.py, tools/smoke_backends.py

NÄCHSTE SCHRITTE
1. Auf Nutzer-Auftrag: 1.0.6 pushen + GitHub-Release v1.0.6 (DEBs+SHA256SUMS
   als Assets) — mit FRISCHEM Token, danach alten Token revoked lassen.
2. Spotify-E2E auf unblockiertem Netz verifizieren (Suche + `spotdl url`).
3. Optional: Gates 4–6 Qt-Migration der historischen Matrizen.
4. Handover nach jeder Session fortschreiben (diese Datei).

WICHTIGE DATEIEN
- casu/spotify.py (Provider: search_spotify/resolve_spotify_url/spotdl_binary)
- casu/locations.py (Spotify→spotdl, YouTube→yt-dlp, Rest passthrough)
- mpcasu_qt/main_window.py (gesamte Qt-UI), mpcasu_qt/app.py (Single-Instance)
- mpcasu_qt/theme.py (Web-Tokens), web/app.js + web/index.html + web_casu.py
- LICENSE 5a (Attribution), THIRD_PARTY_COMPONENTS.md, RELEASE_NOTES_v1.0.*.md
- RELEASE_GATE_STATUS.json (1.0.6, Gates 1–3 PASS, 4–6 PARTIAL)
- packaging/build_debs.sh (Version + Deps), dist/ (nur letzte DEBs getrackt)
