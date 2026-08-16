# START_HIER — Start-Prompt für die neue Portierungs-Session

Öffne eine NEUE Session im Arbeitsverzeichnis `/home/error/Codec-Casu` und
gib den folgenden Text als ersten Prompt ein. Alle nötigen Informationen liegen
bereits in `win-release/` (siehe unten). Ziel: den Windows-Port abarbeiten.

================================================================================
PROMPT (kopiere das Folgende in die neue Session):
================================================================================

Starte den Windows-Port von CASU-CODEC / MPCASU gemäß der bereits fertig
vorbereiteten Planung in `/home/error/Codec-Casu/win-release/`.

Lies ZUERST, in dieser Reihenfolge (alle Pfade relativ zu `/home/error/Codec-Casu`):
1. `win-release/PREREQUISITES.md`   — was beschafft werden muss (SCHRITT 0)
2. `win-release/NAVIGATION.md`      — Karte: wo steht welche Information
3. `win-release/MASTER_GESAMTFAHRPLAN.md` — der abzuarbeitende Einzelfahrplan
4. `win-release/RUN_CHECKLIST.md`   — der fehlerfreie Arbeits-Loop + harte Gates
5. `win-release/REFERENCE_LOOKUP.md` — Schlüsselwort → Datei:Zeile (Nachschlagen)
6. `win-release/PORT_STATUS.md`     — aktueller Stand / aktueller STEP
7. `win-release/roadmap/BLOCKERS.md`— offene Blocker
8. `win-release/WINDOWS_PORT_BASELINE.md` — eingefrorener Referenzstand

VERBINDLICHE GRUNDREGELN (nie verletzen):
- Referenzbaum `/home/error/Codec-Casu` (Code), `/home/error/vlc`,
  `/home/error/webamp-embed` = **READ ONLY** — lesen/ausführen/testen/analysieren
  JA, verändern NIEMALS. Nur `win-release/` ist Schreibgebiet.
- Referenzcode darf ausgiebig gelesen, per grep durchsucht, ausgeführt, mit
  git-Historie analysiert und als Test-Oracle benutzt werden — aber nie geändert.
- Ein Work-Package (WP) pro Iteration. Kein WP als fertig markieren ohne Nachweis
  (Build-Exit, Unit-Ergebnis, echter Wine-Lauf, echtes YouTube/CDN, Golden-Vergleich).
- Fehler nie überspringen: lösen ODER als BLOCKED in `roadmap/BLOCKERS.md` loggen.
- Keine Features still entfernen; keine Dummy-Implementierungen; kein zweiter
  Player/Browser-Fallback für Desktop-Playback.
- Nicht blind Python→C++ transliterieren: Verhalten/Zustände/Ownership/Protokolle
  portieren, nicht Syntax. Python-Äquivalente: QProcess (subprocess),
  QNetworkAccessManager (urllib), QFileInfo/QDir/std::filesystem (pathlib),
  QThread/QtConcurrent (threading), QSqlDatabase/sqlite3 (sqlite3).
- Nicht raten: bei Verständnisfragen Referenz lesen, Git-Historie prüfen,
  Deep-Research in `research/external-research-log.md` dokumentieren.
- Nach jeder größeren Phase: `PORT_STATUS.md` + `WINDOWS_PORT_FEATURE_MATRIX.md`
  + abhakbaren Gesamtfahrplan aktualisieren; `git status --short` prüft Read-only.

SCHRITT 0 — PREREQUISITES (Zuerst, kein Design-Blocker):
- Beschaffe die fehlenden Windows-Runtime-Binaries laut `win-release/PREREQUISITES.md`
  (Qt6-MinGW-DLLs + qwindows.dll, libVLC-Windows + plugins, ffmpeg.exe/ffprobe.exe,
  yt-dlp.exe, zstd, SQLite, MinGW-Runtime) aus offiziellen Quellen und lege sie
  unter `win-release/third_party/` ab; Lizenzen notieren.
- Fehlt etwas und ist nicht sofort beschaffbar → BLOCKED loggen und mit der
  davon unabhängigen Arbeit fortfahren (C++-Core braucht kein Qt).

DANN — ARBEITE DEN GESAMTFAHRPLAN AB (Phasen A→D, Steps 1–42):
- Beginne mit **STEP-001 (WP-REL-001)**: mingw64-Toolchain, Hello-Windows-EXE
  (PE32+ via `x86_64-w64-mingw32-objdump -p`) und unter Wine laufen lassen
  (isolierter `WINEPREFIX=win-release/.wine-test`, ggf. `xvfb-run`).
- Für jedes WP dem Loop folgen: ANALYSIS → Referenz gezielt lesen
  (REFERENCE_LOOKUP → `sed -n '<a>,<b>p'`) → implementieren (nur win-release)
  → cross-compile → unit → wine → compatibility → VERIFIED → nächstes WP.
- Reihenfolge: Foundation (A) → Shared-Core-Libs (B: casu_core→codec/media→
  network→playback→webapi) → Apps (C: CLI→Converter→MPCASU→Web-Backend→Pure-Web)
  → Packaging+Release-Gate (D). Nie WPs aus unterschiedlichen unfertigen Phasen
  mischen; nie weiterspringen bei offenem Fehler.
- Siehe `roadmap/tools/<tool>/PORT_ROADMAP.md` für die maximale Detaillierung
  je Tool und `roadmap/libraries/*` für die Shared-Libs.

HARTE GATES (nie überspringen):
- YouTube/Netzwerk: echtes YouTube/CDN unter Wine (nicht nur Mock).
- GUI/Playback: echter Windows-Build unter Wine + Screenshot-Vergleich Linux↔Wine.
- Codec/Converter: Golden-Vergleich (Hashes/JSON) Linux↔Wine.
- Clean-Prefix: gepacktes Release in NEUEM WINEPREFIX; nur Paket-Inhalt.
- Keine falschen PASS: "kompiliert" ≠ "Unit grün" ≠ "funktioniert".

TYPISCHE STOLPERFALLEN (aus der Analyse; siehe REFERENCE_LOOKUP):
- libVLC-State 6/7 + zero-time-EOF → mpcasu_backend.py:600-627 (nicht erfolgreich
  als Fehler werten).
- YouTube-Lifecycle: stop old → start proxy → open; nie Proxy vor open zerstören.
- VideoSurface: keine Qt-Overlays aufs native Video (Flicker); HWND-Lifetime;
  qwindows.dll; vlc/plugins; ffmpeg arg-arrays; Unicode/Spaces.
- Threading: Qt-GUI nur GUI-Thread, Worker→Signals. Audio: kein PulseAudio → WASAPI/Qt.
- Wine ≠ Windows: Wine-spezifische Workarounds nicht als universelle Lösung coden.

ZIEL: Bis zum unter Wine verifizierten, vollständig paketierten Windows-Release
(`dist/MPCASU-Windows-x86_64.zip`), `WINDOWS_RELEASE_GATE.json` = PASS,
Referenzbaum unverändert. Alle Fahrpläne/Zustände sind dafür bereit.

================================================================================
ENDE PROMPT
================================================================================

## Was die neue Session in win-release/ vorfindet (alles fertig vorbereitet)
- `PREREQUISITES.md` — Beschaffung (SCHRITT 0)
- `NAVIGATION.md` — Index über alle 34+ Hilfsdateien
- `MASTER_GESAMTFAHRPLAN.md` — der Einzelfahrplan (Phasen A–D, Steps 1–42)
- `RUN_CHECKLIST.md` — Arbeits-Loop + Gates + Fehlerbehandlung
- `REFERENCE_LOOKUP.md` — Schlüsselwort → Datei:Zeile
- `PORT_STATUS.md` — aktueller Stand (nächster STEP-001)
- `WINDOWS_PORT_BASELINE.md`, `WINDOWS_PORT_FEATURE_MATRIX.md`
- `research/*` (17 Docs), `roadmap/*` (Master, Critical Path, Execution,
  Dependency/Audit, Coverage, BLOCKERS), `roadmap/tools/<tool>/*`,
  `roadmap/libraries/*`
- `research-tools/completeness_audit.py` (100%-Coverage-Check, re-lesbar)

## Notiz an mich (Kontext)
- Referenz-HEAD: `0b51803` (Stand der Vorbereitung; die neue Session wird
  weitere Commits in `win-release/` hinzufügen).
- Referenzbaum unangetastet; nur `win-release/` + Freeze-Doku geändert.
- Toolchain Linux (cmake/ninja/wine/mingw/python) vorhanden; Qt6-MinGW +
  libVLC-Windows fehlen (→ SCHRITT 0).
