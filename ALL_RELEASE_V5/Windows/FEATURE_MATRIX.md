# FEATURE_MATRIX — Windows ↔ Linux-Referenz (Parität)

Legende: ✅ fertig+verifiziert · 🟡 teilweise (MSVC-only) · 🔲 geplant · ❌ nein

| Feature | Linux-Referenz | Windows |
|---------|---------------|---------|
| Container CASUNAT1/NAT2/MP5 (zstd+zlib) | ✅ | ✅ (Golden byte-identisch) |
| CLI `casu` (alle Subcommands) | ✅ | ✅ |
| Converter (Qt-GUI, Batch, Presets) | ✅ | ✅ |
| Player MPCASU (libVLC) | ✅ | ✅ (echter Decode unter Wine) |
| YouTube (yt-dlp → Loopback → libVLC) | ✅ | ✅ (Live-Gate: Full-Stream 28,5 MB byte-exakt) |
| Web-Backend `/api/*` + Stream-Proxy | ✅ | ✅ |
| Pure Web (frozen, byte-identical) | ✅ | ✅ (SHA verifiziert) |
| Playlist-Formate (M3U/PLS/WPL/XSPF/…+ JSON) | ✅ | ✅ |
| Playlist-Play ohne Ausklappen (ganze Liste durchspielen) | ✅ | ✅ |
| Merge: Dateien/URLs in Playlist (dedupliziert) | ✅ | ✅ |
| Gemischte Queue (Playlists+Dateien+URLs) | ✅ | ✅ |
| Absturzsicherheit (kaputte Playlists etc.) | ✅ | ✅ |
| Visualizer (gedrosselt, kein CPU-Pegel) | ✅ | ✅ |
| MIME/Dateitypen `.casu`/`.mp5` | ✅ (MIME-DB) | ✅ (Registry, unter Wine getestet; echt nur Windows) |
| PATH-Registrierung `casu` | — (n/a) | ✅ (Uninstall-Fix verifiziert) |
| Web-Player-Tabs (Spotify/Hearthis/Tidal/Netflix/Browse) | ✅ (eingebetteter QtWebEngine) | 🟡 MinGW=Stub-Tabs; echt nur MSVC-Build |
| Installer | `.deb` | ✅ NSIS setup.exe |
| MF/DirectShow-Decoder (CODEC-001) | — | 🔲 geplant (BLOCKER-005) |
| GNU/Linux-Build | ✅ | ✅ (Cross-Compile + Wine) |
| macOS | — | 🔲 geplant (Mac-OS/) |
| Android | — | 🔲 geplant (Android/) |

## Paritätsregel
"Exakt gleiche Apps" heißt: gleiche Container, gleiche CLI, gleicher Player,
gleiche Playlist-Queue-Semantik, gleicher eingebetteter Browser (MSVC-Build).
Kein Feature still entfernen; Abweichungen hier dokumentieren (BLOCKED statt verschwinden).