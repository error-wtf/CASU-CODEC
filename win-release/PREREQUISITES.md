# PREREQUISITES — Beschaffung vor dem eigentlichen Portieren

Dieses Dokument listet, was die neue Portierungs-Session VOR der Implementierung
beschaffen muss (kein Design-Blocker, aber nötig für echte Wine-GUI-/Playback-Tests).
Pfad: `win-release/third_party/` ist die vorgesehene Ablage.

## Bereits vorhanden (Linux-Toolchain, Stand 2026-08-16)
| Tool | Version | Zweck |
|------|---------|-------|
| cmake | 4.2.3 | Build |
| ninja | 1.13.2 | Build |
| wine / wine64 | 10.0 | Windows-Runtime-Test |
| x86_64-w64-mingw32-g++ | GCC 13-win32 | MinGW-Cross-Compiler |
| python3.14 | 3.14.4 | Referenz-Tests (Read-only) |
| ffmpeg / ffprobe (Linux) | /usr/bin | Referenz-Helper (nicht für Paket) |
| yt-dlp (Linux) | 2026.03.17 | Referenz-Resolver (nicht für Paket) |

## FEHLT noch (muss beschafft werden) — für echte Windows-Tests/Paket
| Komponente | Warum nötig | Bezugsquelle (offiziell) | Ablage |
|------------|-------------|--------------------------|--------|
| **Qt 6 (MinGW-w64 x86_64) DLLs + qwindows.dll** | GUI/Playback-Exe bauen+ausführen | Qt online installer (MinGW-Abbau) oder aqtinstall-Paket | win-release/third_party/qt/ |
| **libVLC Windows** (libvlc.dll, libvlccore.dll, plugins/) | Embedded-Playback unter Wine | videolan.org Windows-VLC / offizielle libVLC-Distro | win-release/third_party/vlc/ |
| **ffmpeg.exe + ffprobe.exe (Windows)** | Converter/Recording im Paket (QProcess-Helper) | offizielle ffmpeg.org-Windows-Builds (GPL) | win-release/third_party/tools/ |
| **yt-dlp.exe** | YouTube-Resolver im Paket | github.com/yt-dlp/yt-dlp Releases | win-release/third_party/tools/ |
| **zstd (Windows)** | MP5-Kompression (libzstd) | github.com/facebook/zstd Releases | win-release/third_party/zstd/ |
| **SQLite (Windows)** | Library-DB (oder QtSql mitgeliefert) | sqlite.org oder Qt | win-release/third_party/sqlite/ |
| MinGW-Runtime-DLLs (libgcc/libstdc++/winpthreads) | Selbsttragendes Paket | mit MinGW-GCC-Installation | win-release/third_party/mingw/ |

## Ablauf-Empfehlung für die neue Session
1. Zuerst die oben fehlenden Windows-Runtime-Binaries beschaffen und in
   `win-release/third_party/` ablegen (offizielle Quellen, Lizenzen notieren).
2. Parallel (kein Blocker): STEP-001 Toolchain + Hello-Windows-EXE bauen und
   unter Wine laufen lassen (braucht noch KEIN Qt).
3. Erst wenn Qt/libVLC da: mit echten GUI-/Playback-Wine-Tests weitermachen.

## Lizenzen-Hinweis
Vor dem Bundling ins Paket: Lizenzen (Qt LGPL, VLC GPL/LGPL, FFmpeg GPL/LGPL,
zstd BSD, SQLite Public Domain, yt-dlp Unlicense) in
`win-release/third_party/THIRD_PARTY_LICENSES/` ablegen — Policy siehe
`research/completeness-remaining-files.md` (Lizenzen-Abschnitt).
