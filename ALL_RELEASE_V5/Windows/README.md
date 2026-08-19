# MPCASU / CASU-CODEC — Windows Release-Planung (ALL_RELEASE_V5)

Ziel: **Windows x86_64**, C++20 + Qt 6 + CMake + Ninja + MinGW-w64
(MSVC/QtWebEngine-Endbuild optional), NSIS-Installer, verified under Wine.

Kanonische Arbeitskopie: `win-release/` (Code + Build). Dieser Ordner ist die
Release-Planung mit denselben Hilfsdateien wie der Linux-Port.

## Status (2026-08-19)

- **v3.0.0 VERÖFFENTLICHT** — `MPCASU-Setup-3.0.0.exe` + `MPCASU-Windows-x86_64.zip`
  (GitHub-Release v3.0.0, `error-wtf/CASU-CODEC`).
- Release-Gate: **14/14 PASS** (`win-release/dist/WINDOWS_RELEASE_GATE.json`,
  generated_utc 2026-08-19T10:48:55Z).
- ctest unter Wine: **16/16 grün** (inkl. `casu_playlist_test`, 14 Checks).
- Playlist-Queue-Feature (Playlist-Play ohne Ausklappen + Merge in Playlists)
  im ZIP + setup.exe verifiziert (strings-Check).
- **Nächste Version: v5.0.0** (v4.x wird übersprungen — siehe README.md im
  ALL_RELEASE_V5-Root).

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