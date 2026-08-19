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
| Komponente | Warum nötig | Bezugsquelle (offiziell) | Ablage | Status |
|------------|-------------|--------------------------|--------|--------|
| **Qt 6 (MinGW-w64 x86_64) DLLs + qwindows.dll** | GUI/Playback-Exe bauen+ausführen | Qt online installer (MinGW-Abbau) oder aqtinstall-Paket | win-release/third_party/qt/ | **da** (6.8.3 mingw_64) |
| **libVLC Windows** (libvlc.dll, libvlccore.dll, plugins/) | Embedded-Playback unter Wine | videolan.org Windows-VLC / offizielle libVLC-Distro | win-release/third_party/vlc/ | **da** |
| **ffmpeg.exe + ffprobe.exe (Windows)** | Converter/Recording im Paket (QProcess-Helper) | offizielle ffmpeg.org-Windows-Builds (GPL) | win-release/third_party/tools/ | **da** |
| **yt-dlp.exe** | YouTube-Resolver im Paket | github.com/yt-dlp/yt-dlp Releases | win-release/third_party/tools/ | **da** |
| **zstd (Windows)** | MP5-Kompression (libzstd) | github.com/facebook/zstd Releases | win-release/third_party/zstd/ | **da** (zstd.exe) + libzstd.a cross-gebaut |
| **SQLite (Windows)** | Library-DB (oder QtSql mitgeliefert) | sqlite.org oder Qt | win-release/third_party/sqlite/ | offen (Qt6 enthält QtSql) |
| **OpenSSL 3 (Windows DLLs)** | TLS für Qt6Network (HTTPS: YouTube-CDN, Webprovider) | openssl.org / GitHub, am 2026-08-18 aus Quelle für MinGW gebaut | third_party/qt/…/bin/ (libssl-3-x64.dll, libcrypto-3-x64.dll) + plugins/tls/ | **da** |
| MinGW-Runtime-DLLs (libgcc/libstdc++/winpthreads) | Selbsttragendes Paket | mit MinGW-GCC-Installation | win-release/third_party/mingw/ | via Qt-bin bundeln |

## Ablauf-Empfehlung für die neue Session
1. Zuerst die oben fehlenden Windows-Runtime-Binaries beschaffen und in
   `win-release/third_party/` ablegen (offizielle Quellen, Lizenzen notieren).
2. Parallel (kein Blocker): STEP-001 Toolchain + Hello-Windows-EXE bauen und
   unter Wine laufen lassen (braucht noch KEIN Qt).
3. Erst wenn Qt/libVLC da: mit echten GUI-/Playback-Wine-Tests weitermachen.

## Build-Zusatz (Session 2026-08-18)
- **zlib (MinGW)** via `libz-mingw-w64-dev` installiert (für MP5-Deflate/Inflate;
  WP-CORE-005). Gebündelt wird `zlib1.dll` bzw. statisch — Verifikation in
  WP-REL-005/006.
- **zstd (MinGW lib)** am 2026-08-18 aus Quelle (zstd-1.5.7) mit der
  Cross-Toolchain gebaut (`libzstd.a` statisch → `/usr/x86_64-w64-mingw32/`).
  BLOCKER-001 gelöst. WP-CORE-007 VERIFIED: MP5-decompress versucht zstd zuerst,
  dann zlib-Fallback; Writer bleibt zlib (byte-identische Golden-Fixtures).
- **NSIS (makensis)** am 2026-08-19 installiert (`apt install nsis`, v3.10) für
  den `setup.exe`-Installer (`scripts/setup.nsi`). Build: `makensis scripts/setup.nsi`.
- **Installer-Icon** am 2026-08-19: `assets/casu-installer-icon.ico` (aus
  `/home/error/casu-installer-icon.png` 1254×1254 per ImageMagick, 6 Größen 16–256).

## Lizenzen-Hinweis
Vor dem Bundling ins Paket: Lizenzen (Qt LGPL, VLC GPL/LGPL, FFmpeg GPL/LGPL,
zstd BSD, SQLite Public Domain, yt-dlp Unlicense) in
`win-release/third_party/THIRD_PARTY_LICENSES/` ablegen — Policy siehe
`research/completeness-remaining-files.md` (Lizenzen-Abschnitt).
