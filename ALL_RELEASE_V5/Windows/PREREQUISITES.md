# PREREQUISITES — Toolchain + Beschaffung (Windows x86_64)

Pfad: `win-release/third_party/` ist die Ablage. Stand: alles **da** (v3.0.0).

## Vorhanden (Linux-Build-Host, Stand 2026-08-19)
| Tool | Version | Zweck |
|------|---------|-------|
| cmake | 4.2.3 | Build |
| ninja | 1.13.2 | Build |
| wine / wine64 | 10.0 | Windows-Runtime-Test |
| x86_64-w64-mingw32-g++ | GCC 13-win32 | MinGW-Cross-Compiler |
| python3.14 | 3.14.4 | Referenz-Tests (read-only) |
| makensis (NSIS) | 3.10 | setup.exe-Installer |
| ffmpeg/ffprobe, yt-dlp (Linux) | — | Referenz-Helfer |

## Windows-Runtime (third_party/, gebündelt im Paket)
| Komponente | Version | Ablage |
|------------|---------|--------|
| Qt 6 (MinGW-w64 x86_64) + qwindows.dll | 6.8.3 | `third_party/qt/6.8.3/mingw_64/` |
| libVLC (libvlc.dll + plugins/) | 3.0.21 | `third_party/vlc/` |
| ffmpeg.exe + ffprobe.exe | offiziell | `third_party/tools/` |
| yt-dlp.exe | aktuell | `third_party/tools/` |
| zstd | 1.5.7 (lib aus Quelle gebaut) | `third_party/zstd/` |
| OpenSSL 3 (TLS, aus Quelle für MinGW gebaut) | 3.4.1 | `third_party/qt/…/bin/` + `plugins/tls/` |
| MinGW-Runtime-DLLs (libgcc/libstdc++/winpthreads) | via Qt-bin | `third_party/mingw/` |
| NSIS + Installer-Icon | 3.10; `assets/casu-installer-icon.ico` | — |

## Für v5.0 (Windows) offen
- MSVC/QtWebEngine-Endbuild auf echtem Windows-PC (Visual Studio 2022):
  `scripts/build-msvc.bat` + `CMakePresets.json` (lädt Qt 6.8.3 MSVC x64 inkl.
  QtWebEngine via aqtinstall automatisch). Hier (Linux) nicht baubar.

## Lizenzen
Vor dem Bundling: Qt LGPL, VLC GPL/LGPL, FFmpeg GPL/LGPL, zstd BSD, SQLite
Public Domain, yt-dlp Unlicense → `win-release/third_party/THIRD_PARTY_LICENSES/`
(im Paket enthalten, Gate `licenses`).