# FEATURE_MATRIX — Linux (Referenz = Linux-Referenzplayer selbst)

Die Linux-Version ist der **Referenzstand** — hier gilt: kein Feature fehlt
per Definition; die Matrix dient dem Abgleich mit Windows und der Doku.

| Feature | Linux | Windows (Parität) |
|---------|-------|-------------------|
| Container CASUNAT1/NAT2/MP5 | ✅ | ✅ (Golden byte-identisch) |
| CLI `casu` | ✅ | ✅ |
| Converter Qt-GUI | ✅ | ✅ |
| Player MPCASU (libVLC) | ✅ | ✅ |
| YouTube (yt-dlp→Loopback→libVLC) | ✅ | ✅ (Live-Gate) |
| Web-Backend `/api/*` | ✅ | ✅ |
| Pure Web (frozen) | ✅ | ✅ (byte-identisch) |
| Playlist-Formate + Queue + Merge | ✅ | ✅ |
| Visualizer gedrosselt | ✅ | ✅ |
| MIME `.casu`/`.mp5` | ✅ (MIME-DB) | ✅ (Registry) |
| Eingebetteter Browser (QtWebEngine) | ✅ | 🟡 MinGW=Stub, MSVC=echt |
| Installer | ✅ DEB | ✅ NSIS setup.exe |

## Verhaltens-Parität (verbindlich)
- Gleiche Container/CLI-Ergebnisse (Golden byte-identisch).
- Gleiche Playlist-Queue-Semantik (Playlist-Play, Merge dedupliziert, gemischte
  Queue, Absturzsicherheit).
- Gleicher eingebetteter Browser (nur MSVC-Build hat echten Chromium).