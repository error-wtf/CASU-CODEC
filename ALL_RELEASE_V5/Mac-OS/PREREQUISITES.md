# PREREQUISITES — Toolchain + Beschaffung (macOS)

Status: **noch nichts beschafft** (Projekt geplant, kein macOS-Host).

## Benötigt (Beschaffungsliste für den ersten macOS-Build)
| Komponente | Bezugsquelle | Zweck |
|------------|--------------|-------|
| macOS-Host (Apple Silicon oder Intel) ODER CI-Runner `macos-latest` | GitHub Actions / eigene Hardware | Build + Test |
| Qt 6 (macOS, inkl. **QtWebEngine**) | qt.io (aqtinstall) / Homebrew | GUI + eingebetteter Browser |
| libVLC (macOS) | videolan.org | Playback |
| ffmpeg + ffprobe (macOS) | offiziell (ffmpeg.org, GPL) | Converter/Recording |
| yt-dlp | github.com/yt-dlp/yt-dlp | YouTube-Resolver |
| zstd (macOS) | github.com/facebook/zstd | MP5-Kompression |
| OpenSSL 3 (macOS) | openssl.org / Homebrew | TLS für Qt6Network |
| cmake + ninja | Homebrew | Build |
| Xcode Command Line Tools | Apple | clang/Linker |
| Developer-ID-Zertifikat (+ Notarisierung) | Apple Developer | Codesign für Verteilung |

## Lizenz-Hinweis
Wie bei Windows/Linux: Qt LGPL, VLC GPL/LGPL, FFmpeg GPL/LGPL, zstd BSD,
SQLite Public Domain, yt-dlp Unlicense — Lizenzen ins Bundle aufnehmen
(`THIRD_PARTY_LICENSES/`), Gate `licenses` analog Windows.