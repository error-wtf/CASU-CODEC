# FEATURE_MATRIX — macOS (Ziel-Parität, noch nicht gebaut)

Legende: 🔲 geplant · ✅ Ziel (Parität wie Windows/Linux)

| Feature | Ziel |
|---------|------|
| Container CASUNAT1/NAT2/MP5 | 🔲 (Golden byte-identisch) |
| CLI `casu` | 🔲 (identische Subcommands) |
| Converter (Qt-GUI, Batch, Presets) | 🔲 |
| Player MPCASU (libVLC) | 🔲 |
| YouTube (yt-dlp→Loopback→libVLC) | 🔲 (echter Stream) |
| Web-Backend `/api/*` | 🔲 |
| Pure Web (frozen) | 🔲 (byte-identisch im Bundle) |
| Playlist-Formate + Queue + Merge | 🔲 (gleiche Semantik) |
| Visualizer gedrosselt | 🔲 |
| Dateitypen `.casu`/`.mp5` | 🔲 (Info.plist CFBundleDocumentTypes) |
| Eingebetteter Browser (QtWebEngine) | 🔲 **voll** (Qt bietet WebEngine für macOS) |
| Installer | 🔲 `.dmg` (+ Codesign/Notarisierung) |
| Universal (arm64 + x86_64) | 🔲 |

## Paritätsregel
Gleiche Container/CLI/GUI/Queue-Semantik wie Linux + Windows; eingebetteter
Browser voll (kein Stub). Kein Feature still entfernen.