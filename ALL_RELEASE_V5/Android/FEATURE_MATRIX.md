# FEATURE_MATRIX — Android (Ziel-Parität, noch nicht gebaut)

Legende: 🔲 geplant · ✅ Ziel

| Feature | Ziel |
|---------|------|
| Container CASUNAT1/NAT2/MP5 | 🔲 (als .so; Golden-Identität) |
| CLI `casu` | 🔲 (kein Shell → Kern-Logik als .so für andere Apps) |
| Converter | 🔲 (Touch-UI, optional) |
| Player MPCASU | 🔲 (Qt-GUI, libVLC, Touch) |
| YouTube (yt-dlp→Loopback→libVLC) | 🔲 **Entscheidung nötig** (Transport auf Android) |
| Web-Backend `/api/*` | 🔲 (in-App Loopback) |
| Pure Web | 🔲 (Assets im APK, in WebEngine-Tab) |
| Playlist-Formate + Queue + Merge | 🔲 (gleiche Semantik, touch-gerecht) |
| Visualizer gedrosselt | 🔲 |
| Dateitypen `.casu`/`.mp5` | 🔲 (Intent-Filter im Manifest) |
| Eingebetteter Browser (QtWebEngine) | 🔲 **voll** (Qt bietet WebEngine für Android) |
| Installer | 🔲 `.apk` / `.aab` (signiert) |
| ABIs | 🔲 arm64-v8a + armeabi-v7a + x86_64 |

## Paritätsregel
Gleiche Container-/Format-Semantik (Golden); UI darf touch-bedingt abweichen
(nur mit Nutzer-Freigabe). Kein Feature still entfernen.