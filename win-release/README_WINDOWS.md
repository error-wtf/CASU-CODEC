# MPCASU / CASU-CODEC — Windows Port (win-release)

Target: **C++20 + Qt 6 + CMake + Ninja + MinGW-w64**, Windows x86_64,
cross-compiled under Linux, verified under Wine.

This directory is the **only write area** of the frozen repository. The rest
of `/home/error/Codec-Casu` is the read-only reference (specification, test
oracle, design reference).

## Status (2026-08-18)

- Baseline frozen: `WINDOWS_PORT_BASELINE.md` (HEAD `2367dcbc`, 400 tests PASS)
- Pure Web Release 3.0.0 frozen (SHA256 in `dist/SHA256SUMS`)
- **Phase A (Foundation) VERIFIED** — Toolchain, CMake/dependencies/packaging,
  Build-Script, Wine-Harness, DLL-Audit, Lizenzen, Runtime-Beschaffung.
- **Phase B (Shared-Core) VERIFIED** — casu_core (SHA256/Formats/Manifest/
  CASUNAT1/CASUNAT2/MP5(zstd+zlib)/Sidecar), casu_codec, casu_media,
  casu_network, casu_playback (inkl. echtem libVLC-Decode), casu_webapi.
- **Phase C (Apps) implementiert + Wine-Tests grün** — casu.exe (CLI),
  CASU-Converter.exe, MPCASU.exe, CASU-Web-Backend.exe.
- **Test-Suite:** 13/13 ctest grün unter Wine (`.wine-test`).
- **Offen:** echter-YouTube-Wine-Gate (STEP-032), CLI-Journal/Resume (STEP-022),
  formalisierte Golden-Fixtures (STEP-014), Phase-D-Gates (Clean-Prefix,
  WINDOWS_RELEASE_GATE.json, Reproduzierbarkeit). Siehe `PORT_STATUS.md` +
  `roadmap/BLOCKERS.md`.

## Build (Linux → Windows)

```sh
cmake -S . -B build-win64 -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE=cmake/mingw64-toolchain.cmake -DCMAKE_BUILD_TYPE=Release
cmake --build build-win64            # PE32+ EXEs
ctest --test-dir build-win64         # unter Wine (isolierter Prefix .wine-test)
./scripts/build-windows-release.sh   # configure→build→test→stage→zip→sha256→gate
```

## Deliverable

```
dist/MPCASU-Windows-x86_64.zip
    MPCASU.exe
    CASU-Converter.exe
    CASU-Web-Backend.exe
    casu.exe
    Qt6*.dll
    plugins/platforms/qwindows.dll
    vlc/ (libvlc.dll + plugins/)
    tools/ (ffmpeg.exe, ffprobe.exe, yt-dlp.exe)
    web/pure/        (byte-identical Pure Web Release 3.0.0)
    LICENSE, THIRD_PARTY_LICENSES/, README_WINDOWS.md

dist/MPCASU-Setup-3.0.0.exe      (NSIS installer: full install + shortcuts + uninstaller)
```

## Installation (Windows)

Einfachste Variante: **`MPCASU-Setup-3.0.0.exe`** ausführen. Der NSIS-Installer
(mit CASU-Icon) legt alles nach `%ProgramFiles%\MPCASU`, erstellt Startmenü- und
Desktop-Verknüpfungen und einen Uninstaller. Alternativ das ZIP nach einem
beliebigen Ordner entpacken und `MPCASU.exe` starten (portable).

### Update & Rechte (ab diesem Build)

- **Auto-Update:** Eine bestehende Installation wird erkannt (Registry,
  Machine- UND Per-User-Scope) und **in-place aktualisiert** — laufende
  Apps werden automatisch geschlossen, es entsteht keine Zweitinstallation.
- **Kein Administrator nötig:** Der Installer erzwingt keine UAC-Erhöhung.
  - Gestartet mit Admin-Rechten → Machine-Installation
    (`C:\Program Files\MPCASu`, HKLM, System-PATH).
  - Gestartet ohne Admin-Rechte → **Per-User-Installation**
    (`%LocalAppData%\MPCASU`, HKCU, Benutzer-PATH) — vollständig ohne
    Rechteausweisung nutzbar.
  - Ist eine alte Machine-Installation vorhanden, aber ohne Schreibrecht,
    fällt der Installer auf eine frische Per-User-Installation zurück statt
    zu scheitern.
- **Pro-App-Icons:** Jede App hat ihr eigenes Icon (EXE-Ressource +
  Verknüpfung): MPCASU = Player-Icon, Converter = Converter-Icon,
  Web-Backend = Web-CASU-Icon — identisch zu den Linux-Desktop-Einträgen.

## Embedded web-player browser

Die Web-Provider-Tabs (Spotify/Hearthis/Tidal/Netflix/BROWSE) laufen im
**eingebetteten Browser direkt in der App** — exakt wie die Linux-Version,
kein externer Browser, kein Link-out.

- **Windows (MinGW-Build):** Microsoft Edge **WebView2** (auf Windows 10/11
  praktisch immer vorhanden, inklusive DRM/Widevine → Netflix/Tidal/Spotify
  spielen wirklich ab). Persistente Logins je Provider
  (`%APPDATA%\CASU\webview2\<provider>`), wie beim Linux-QWebEngine-Profil.
  Fehlt die WebView2-Runtime, zeigt der Tab einen Hinweis + Button „im
  Standardbrowser öffnen" (kein leerer Tab).
- **MSVC/QtWebEngine-Build (alternativ):** `scripts/build-msvc.bat` auf einem
  Windows-PC mit Visual Studio 2022 + Python ausführen. Siehe CMakePresets.json.

YouTube läuft **nicht** über einen Browser-Tab, sondern über die
yt-dlp → Loopback → libVLC-Pipeline (identisch zu Linux).

## Apps

| App | EXE | Anmerkung |
|-----|-----|-----------|
| CLI | `casu.exe` | alle Subcommands (kind/verify/info/pack/pack-mp5/mp5-info/native-info/export/media/validate/…) |
| Converter | `CASU-Converter.exe` | Qt-GUI, Batch, Presets, CASU Import/Export |
| Player | `MPCASU.exe` | Qt-GUI, libVLC-Playback, YouTube-Transport, Playlist/Library/EPG/Visualizer |
| Web-Backend | `CASU-Web-Backend.exe` | Loopback-HTTP, /api/*, Stream-Proxy, TranscodeStore |

## Pure Web (frozen, byte-identical)

The pure web player is **not** ported — it is frozen and shipped as-is
(`web/pure/`, SHA256 verified against `MPCASU-PURE-WEB-3.0.0.zip`,
`b71b5d0b3ecde8dd7d2098665f94c4381abd6815a9727019adcc009f68ebf8de`).

### Start (Windows)

- **Einfach:** `web/pure/index.html` im Browser öffnen (Datei-Dialog) —
  funktioniert für lokale Playlists/RADIO.m3u und YouTube via IFrame API.
- **Voll (YouTube-Streaming/CORS/HLS):** `CASU-Web-Backend.exe` starten und
  im Browser `http://127.0.0.1:8497/web/` öffnen. Das Backend serviert
  `web/pure/` und stellt die /api/*-Endpoints bereit.
- Keine Änderungen an den Frozen-Dateien; Packaging-Belange nur dokumentieren.

## Working method

1. Read reference code thoroughly (read-only).
2. Analyze → port one module → cross-compile → unit test → Wine test →
   compare to reference → mark VERIFIED → next module.
3. Never modify anything outside `win-release/`.
4. Never claim PASS without runtime evidence.