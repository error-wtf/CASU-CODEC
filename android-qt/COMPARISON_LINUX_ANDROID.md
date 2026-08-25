# VERGLEICH — Linux MPCASU vs. Android APK (Stand 25.08.2026)

Ehrlicher Vollvergleich. Der Android-APK-Stand ist der WebView-Shell-Build
(v5.0.0 online). Der Neubau „Linux-Player auf Android" läuft unter
`android-qt/` (siehe dortige README — Phase 1 wartet auf die
PySide6-Android-Wheels aus dem Qt-Account).

## Architektur

| | Linux MPCASU | Android APK (aktuell) |
|---|---|---|
| Player | PySide6-Desktop-App, libVLC, voller casu-Stack | WebView-Shell um Pure-Web-UI + Java-Bridges |
| Bewertung | Referenz | ~40–50 % der Funktionen, <20 % der Tiefe |

## Wiedergabe & Formate

| Funktion | Linux | Android |
|---|---|---|
| libVLC (mkv/flac/avi/wma/aiff/alac/rtsp/rtmp/udp) | ✅ | ❌ (nur WebView-Codecs) |
| CASUNAT2 nativ (Scheduler/Seek-Index/Untertitel/Kapitel) | ✅ | teilweise (WASM) |
| CASU Legacy / MP5 / Sidecars | ✅ | teilweise (WASM) |
| Transcode-Fallback (ffmpeg) | ✅ | ❌ |
| Recording (ffmpeg -c copy, Split) | ✅ | ❌ |
| YouTube: Suche + yt-dlp-Resolve + Direktplay | ✅ | ❌ (IFrame + Best-Effort-Scraper) |
| Spotify-Resolve | ✅ | ❌ |
| Radio/HLS | ✅ | ✅ (same-origin Relay) |

## Bibliothek & Metadaten

| Funktion | Linux | Android |
|---|---|---|
| Watched Folders (Verwaltung) | ✅ | ❌ (fixer Auto-Scan) |
| SQLite: Tags, Progress, Resume | ✅ | ❌ |
| Cover-Extraktion + Thumbnails | ✅ | ❌ |
| Snapshot (Videoframe PNG) | ✅ | ❌ |

## VIZ

| Funktion | Linux | Android |
|---|---|---|
| Live-Spektrum | ✅ | ✅ (AnalyserNode, latenzfrei) |
| FFT aus dekodiertem PCM + Overview-Peaks | ✅ | ❌ |
| Cover-Overlay | ✅ | ❌ (nur Playlist-Thumbnails) |
| Track-State-Dateien (CASU) | ✅ | ❌ |

## Queue, EPG, UI-Tiefe

| Funktion | Linux | Android |
|---|---|---|
| Multi-Select + Playlist-Gruppen (non-destruktiv) | ✅ | ❌ |
| M3U/PLS/XSPF/JSPF/ASX/JSON laden **und speichern** | ✅ | nur M3U-Import |
| EPG XMLTV + Guide | ✅ | teilweise |
| A-B-Loop, Chapters, Untertitel, Audio-Delay | ✅ | ❌ |
| Diagnostics, Start-Status+VLC-Version, Converter-ETA | ✅ | ❌ |
| Dateien öffnen (Picker + „Öffnen mit") | ✅ | ✅ (neu) |
| Library Auto-Scan | ✅ (watched folders) | ✅ (fixe Ordner, library.m3u) |

## Web-Browsing & Online

| Funktion | Linux | Android |
|---|---|---|
| Provider-Web-Player (Spotify/Tidal/Netflix/HearThis/Browse) eingebettet mit Sessions | ✅ (QtWebEngine-Tabs) | ✅/⚠️ (WebView-Navigation, BACK=goBack, Cookies) |
| YouTube-Suche | ✅ (yt-dlp) | ⚠️ (Java-Scraper, best-effort) |
| Remote-Playlists/EPG per URL | ✅ | ✅ (Catalog-Relay) |

## System-Integration

| Funktion | Linux | Android |
|---|---|---|
| MPRIS / Media-Notification | ✅ MPRIS | ✅ Media-Notification + MediaSession |
| Widget | ❌ | ✅ 4×1 |
| „Öffnen mit" aus File-Explorern | ✅ (MIME) | ✅ (VIEW-Filter, neu) |
| Launcher-Icon, Installer | ✅ DEB | ✅ APK signiert |

## CASU-Tools

| Funktion | Linux | Android |
|---|---|---|
| validate / verify / info | ✅ CLI+GUI | ✅ JNI (detect/verify/extract) |
| convert / export | ✅ | ❌ |

## Der Weg zu „alles" (android-qt/)

Der Neubau mit dem **echten Linux-Player-Code** (PySide6-on-Android) schließt
die Lücken strukturell: libVLC-Android bringt die Formate, das bundled Python
bringt yt-dlp, der Shim-Layer ersetzt ffprobe/ffmpeg, die Qt-UI bekommt
Small-Screen-Adapter. Blocker: die PySide6-Android-Wheels (Qt-Account nötig) —
Details in `android-qt/README.md`.
