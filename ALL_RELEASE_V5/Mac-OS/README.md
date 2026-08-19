# MPCASU / CASU-CODEC — macOS Release-Planung (ALL_RELEASE_V5)

Ziel: **macOS** (Universal: arm64 + x86_64), C++20 + Qt 6 + CMake, libVLC,
NSIS-Analogon `.dmg`, eingebetteter QtWebEngine (Qt liefert WebEngine für
macOS offiziell — volle Linux-Parität möglich).

Status: **geplant, noch nicht gebaut.** Dieser Ordner ist die Vorbereitung
mit denselben Hilfsdateien wie Windows/Linux.

## Status (2026-08-19)

- Kein macOS-Build vorhanden. Kein macOS-Host verfügbar (Build auf macOS-PC
  oder CI mit `macos-latest` Runner).
- Zielartefakt: `MPCASU-macOS-5.0.0.dmg` (Universal) + optional ZIP.
- Abhängigkeiten: Qt 6 (macOS, inkl. QtWebEngine), libVLC (macOS),
  ffmpeg/ffprobe (macOS), yt-dlp, zstd, OpenSSL 3.

## Build (Plan)

```sh
# Auf macOS-PC oder CI (macos-latest, arm64 + x86_64 → Universal):
brew install qt libvlc ffmpeg yt-dlp zstd openssl cmake ninja
cmake -S . -B build-macos -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build-macos
cpack -G DragNDrop   # → MPCASU-macOS-5.0.0.dmg
```

- Codesign + Notarisierung (Developer-ID) für Verteilung außerhalb des App-Stores.
- QtWebEngine: **verfügbar für macOS** → eingebetteter Browser mit echter
  Linux-Parität (anders als MinGW-Stub).

## Apps (Ziel)

| App | Binary | Anmerkung |
|-----|--------|-----------|
| CLI | `casu` | identische Subcommands wie Linux/Windows |
| Converter | `CASU-Converter.app` | Qt-GUI |
| Player | `MPCASU.app` | Qt-GUI + libVLC + WebEngine-Tabs |
| Web-Backend | `CASU-Web-Backend.app` | Loopback-HTTP `/api/*` |

## Offene Punkte (v5.0, nach Nutzer-Freigabe)
- macOS-Host/CI verfügbar machen.
- Codesign-Zertifikat + Notarisierung.
- Golden-Parität (Hashes/JSON) macOS ↔ Linux/Windows sicherstellen.