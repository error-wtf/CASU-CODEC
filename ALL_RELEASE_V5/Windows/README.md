# MPCASU / CASU-CODEC — Windows Release-Planung (ALL_RELEASE_V5)

Ziel: **Windows x86_64**, C++20 + Qt 6 + CMake + Ninja + MinGW-w64
(MSVC/QtWebEngine-Endbuild optional), NSIS-Installer, verified under Wine.

Kanonische Arbeitskopie: `win-release/` (Code + Build). Dieser Ordner ist die
Release-Planung mit denselben Hilfsdateien wie der Linux-Port.

## Status (2026-08-20)

- **v3.0.0 VERÖFFENTLICHT** — `MPCASU-Setup-3.0.0.exe` + `MPCASU-Windows-x86_64.zip`
  (GitHub-Release v3.0.0, `error-wtf/CASU-CODEC`).
- Release-Gate: **14/14 PASS** (`win-release/dist/WINDOWS_RELEASE_GATE.json`,
  generated_utc 2026-08-19T10:48:55Z).
- **Playlist-Gruppen-Semantik (nicht-destruktiv, implementiert + getestet):**
  `playlist_view_` ist jetzt ein QTreeWidget — Playlists erscheinen als
  sichtbare, auf-/zuklappbare Gruppenzeilen und werden beim Spielen **nie
  aufgelöst**. Die Wiedergabe läuft über die logische Sequenz
  (`logical_sequence()` — Gruppen laufen in ihre Einträge auf, lose
  Dateien/URLs dazwischen, inkl. Shuffle/Repeat). Gruppen + Mehrfachauswahlen
  (Strg/Shift) verschiebbar (↑/↓, Kontextmenü "Move up/down", Block-Move via
  `move_many`); Einträge ein- ("Save selection to playlist…"/"Move to
  playlist…", dedupliziert) und aussortierbar ("Remove from playlist");
  Batch-Dedup (Playlist + eigene Dateien → kein Doppelt-Laden). Test:
  `casu_playlist_test.exe` unter Wine — **ALL PASS** (40 Checks, 2026-08-20).
- ctest unter Wine: **14/14 grün** (ohne `casu_playback_vlc_test`/
  `casu_playback_youtube_live_test` — kein Audio-Gerät/kein Live-Netz), inkl.
  `casu_playlist_test` mit der Gruppen-Semantik (2026-08-20).
- **Web-Player (web-casu `/web/` + Pure Web) tragen dieselbe Gruppen-Semantik**
  (implementiert + getestet): Gruppen bleiben sichtbar (auf-/zuklappbar),
  Gruppen-Tools im Header (▶/↑/↓/×) + Kontextmenü, Mehrfachauswahl Block-Move,
  "Save selection to playlist…" (rein), "Remove from playlist" (raus),
  Re-Add-Dedup. Geprüft: Node-Unit-Harness ALL PASS (17 + 12 Checks) +
  Playwright-Smoke `tools/smoke_web_playlist.py` (mehrfach grün).
  `win-release/web/pure/` byte-identisch aktualisiert
  (`MPCASU-PURE-WEB-3.0.0.zip` neu, SHA `6d6d7bf8…`).
- **Nächste Version: v5.0.0** (v4.x wird übersprungen — siehe README.md im
  ALL_RELEASE_V5-Root).

## Playlist-Gruppen-Semantik (Kurzform)

1. Playlist wählen (Choose files/Load) → EINE Gruppenzeile "[Playlist] Name".
2. Spielen (Doppelklick auf Gruppe = erste Eintrag, auf Kind = genau dieser
   Eintrag) → Gruppe bleibt stehen; logische Sequenz spielt weiter.
3. ↑/↓ bzw. Kontextmenü verschiebt Gruppen und Mehrfachauswahlen (Block).
4. "Save selection to playlist…"/"Move to playlist…" sortiert ein (rein);
   "Remove from playlist" sortiert Kinder aus (raus).
5. Lose Dateien/URLs (ohne Playlist) werden überall in der Queue mitgespielt.
6. Playlist + eigene Dateien zusammen gewählt → kein Doppelt-Laden (Batch-Dedup).

Details: siehe `ALL_RELEASE_V5/README.md` → "Playlist-Gruppen-Semantik".

## Build (Linux → Windows)

```sh
cmake -S . -B build-win64 -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE=cmake/mingw64-toolchain.cmake -DCMAKE_BUILD_TYPE=Release
cmake --build build-win64            # PE32+ EXEs
ctest --test-dir build-win64         # unter Wine (Prefix .wine-test)
./scripts/build-windows-release.sh   # configure→build→test→stage→zip→sha256→gate
```

Hinweis (bekannter Skript-Bug): Schritt 7b (makensis) erwartet das ZIP in
`dist/_stage/`, CPack legt es nach `dist/`. Workaround:
`mkdir -p dist/_stage && (cd dist/_stage && unzip -oq ../MPCASU-Windows-x86_64.zip)`,
dann `makensis scripts/setup.nsi`. Danach sha256 + `release_gate.sh` manuell.

## Deliverable (v3.0.0; bei v5.0: Dateinamen mit 5.0.0)

```
dist/MPCASU-Windows-x86_64.zip      (portabel, exe + Qt6 + libVLC + tools + web/pure/)
dist/MPCASU-Setup-3.0.0.exe         (NSIS: %ProgramFiles%\MPCASU, Startmenü/Desktop, Uninstaller)
dist/WINDOWS_RELEASE_GATE.json      (14 Gates)
dist/SHA256SUMS                     (zip + setup)
```

## Installation (Windows)

- `MPCASU-Setup-3.0.0.exe` → installiert nach `%ProgramFiles%\MPCASU`,
  PATH-Registrierung (`casu`), Dateitypen `.casu`/`.mp5` → MPCASU, Uninstaller.
- Oder ZIP entpacken und `MPCASU.exe` starten (portabel).
- PATH/Dateitypen: nur auf echtem Windows endgültig verifizierbar (Wine ok).

## Embedded web-player browser

- Web-Provider-Tabs (Spotify/Hearthis/Tidal/Netflix/BROWSE) im eingebetteten
  QtWebEngine-Browser (Linux-Parität). MinGW-Paket = Stub-Tabs; echter Chromium
  nur im MSVC-Build (`scripts/build-msvc.bat` + `CMakePresets.json`).
- YouTube: yt-dlp → Loopback → libVLC (kein Browser-Tab).

## Apps

| App | EXE | Anmerkung |
|-----|-----|-----------|
| CLI | `casu.exe` | alle Subcommands (kind/verify/info/pack/pack-mp5/…) |
| Converter | `CASU-Converter.exe` | Qt-GUI, Batch, Presets |
| Player | `MPCASU.exe` | Qt-GUI, libVLC, YouTube-Transport, Playlist/Library/EPG/Visualizer |
| Web-Backend | `CASU-Web-Backend.exe` | Loopback-HTTP `/api/*`, Stream-Proxy |

## Pure Web (frozen, byte-identical)

`web/pure/` im Paket, SHA256 `b71b5d0b…` (MPCASU-PURE-WEB-3.0.0.zip).
Start: `web/pure/index.html` direkt öffnen, oder Backend + `http://127.0.0.1:8497/web/`.

## Working method

1. Referenz lesen (read-only) → portieren → cross-compile → unit → wine →
   Vergleich → VERIFIED.
2. Nie PASS ohne Laufzeit-Nachweis; Gates in `RUN_CHECKLIST.md` beachten.
3. Vor Änderungen: `SAFE-GUARD.md` (Backup + Tests).