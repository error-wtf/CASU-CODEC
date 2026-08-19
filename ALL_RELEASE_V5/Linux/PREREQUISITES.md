# PREREQUISITES — Toolchain + Beschaffung (Linux)

Build-Host ist Ubuntu 26.04 LTS x86_64. Alles **vorhanden** (Stand 2026-08-19).

## Toolchain
| Tool | Version | Zweck |
|------|---------|-------|
| python3 | 3.14.4 | Player/CLI-Referenz (mpcasu_qt, casu) |
| PyQt6 / PySide6 | installiert | Qt-Desktop-Player |
| pytest | installiert | Tests |
| xvfb | installiert | UI-Tests ohne Display |
| dpkg-deb | installiert | DEB-Paketbau |
| ffmpeg/ffprobe | /usr/bin | Converter/Recording-Helfer |
| yt-dlp | 2026.03.17 | YouTube-Resolver |
| x86_64-w64-mingw32-g++ | GCC 13-win32 | Windows-Cross-Build (Paritätstest) |
| wine / wine64 | 10.0 | Windows-Test-Harness |
| cmake / ninja | 4.2.3 / 1.13.2 | Windows-Build |
| makensis (NSIS) | 3.10 | Windows-Installer |

## Paketbau (DEBs)
- `packaging/build_debs.sh` → 4 Pakete (casu-codec, casu-converter, mpcasu,
  web-casu). Dependencies im DEB: python3, python3-pyqt6 (o.ä.), ffmpeg, yt-dlp.
- MIME: `packaging/casu-codec-mime.xml`; postinst führt
  `update-mime-database` + `update-desktop-database` aus.

## Für v5.0 (Linux) offen
- AppImage/Snap/Flatpak (optional, Nutzer-Entscheid).
- arm64-Build (optional).

## Lizenzen
Siehe `THIRD_PARTY_COMPONENTS.md` im Repo-Root (Qt LGPL, VLC GPL/LGPL,
FFmpeg GPL/LGPL, zstd BSD, SQLite Public Domain, yt-dlp Unlicense).