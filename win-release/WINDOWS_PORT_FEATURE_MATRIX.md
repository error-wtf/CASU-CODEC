# WINDOWS PORT FEATURE MATRIX

Status: `NOT_STARTED` | `ANALYSIS` | `IMPLEMENTING` | `BUILDING` | `TESTING` |
`WINE_TESTING` | `BLOCKED` | `VERIFIED`

"VERIFIED" requires runtime evidence (Wine GUI/playback, real YouTube/CDN,
golden comparison) — never a mock-only PASS.

Stand: 2026-08-18. Alle Kern-Features sind unter Wine verifiziert (Unit +
Golden + echtes Playback/CDN). Einige Rand-Features (SQLite-Library-DB,
EPG-Datenbank, Recording-Datei-Output) sind implementiert, aber nicht als
eigener Windows-Test abgedeckt → `IMPLEMENTING`/`NOT_TESTED`, kein falscher
PASS.

| ID | Feature | Reference | Windows target | Unit | Integration | Wine | Status |
|----|---------|-----------|----------------|------|-------------|------|--------|
| CASU-001 | CASU container parse/write | casu/core.py, fileio, schema | casu_core (C++) | ✓ | ✓ | ✓ | VERIFIED |
| CASU-002 | Manifest + checksums | casu/schema.py | casu_core | ✓ | ✓ | ✓ | VERIFIED |
| CASU-003 | CASUNAT1 decode | casu/native.py | casu_core | ✓ | ✓ (golden SHA) | ✓ | VERIFIED |
| CASU-004 | CASUNAT2 native | casu/native_v2 | casu_core | ✓ | ✓ (1032 chunks/seek/integrity) | ✓ | VERIFIED |
| CASU-005 | MP5 / legacy | casu/mp5 | casu_core | ✓ | ✓ (golden 5 chunks) | ✓ | VERIFIED |
| CASU-006 | Segments/scheduler/tiles | casu/scheduler, tiles | casu_core | ✓ | – | ✓ | VERIFIED (sidecar resolve) |
| CASU-007 | zstd compression | casu (zstd) | casu_core (+zstd) | ✓ | ✓ | ✓ | VERIFIED |
| PLAY-001 | Open local media | LibVLCBackend.open_source | LibVLCBackend C++ | ✓ | ✓ (echter Decode) | ✓ | VERIFIED |
| PLAY-002 | Play/Pause/Resume/Stop | mpcasu_playback.py | PlaybackController | ✓ | ✓ | ✓ | VERIFIED |
| PLAY-003 | Seek/duration/position | backend | backend | ✓ | ✓ | ✓ | VERIFIED |
| PLAY-004 | Volume/Mute/Rate | backend | backend | ✓ | ✓ | ✓ | VERIFIED |
| PLAY-005 | VideoSurface native embed | videoframe.py | QWidget + HWND | ✓ | ✓ (smoke) | ✓ | VERIFIED |
| PLAY-006 | Tracks/subtitles/chapters | backend | backend | ✓ | – | ✓ | VERIFIED (interface) |
| PLAY-007 | Snapshot | backend | backend | – | – | – | NOT_TESTED |
| PLAY-008 | Fullscreen/DPI/resize | main_window | Qt6 | – | – | ✓ (smoke) | IMPLEMENTING |
| PLAY-009 | Native CASU playback | mpcasu_native_backend | NativeCasuBackend | – | – | – | IMPLEMENTING |
| PLAY-010 | Visualizer | main_window | Qt/audio | ✓ (FFT/wave) | – | ✓ | VERIFIED (Unit) |
| YT-001 | yt-dlp resolve (QProcess) | casu/locations.py | yt-dlp.exe + QProcess | ✓ | ✓ (Live-CDN) | ✓ | VERIFIED |
| YT-002 | Loopback transport (Range/206) | youtube_proxy.py | QTcpServer/QNAM | ✓ | ✓ (Live-CDN Bytes) | ✓ | VERIFIED |
| YT-003 | YouTube playback via libVLC | main_window | LibVLCBackend | ✓ | ✓ (Live-Gate) | ✓ | VERIFIED |
| WP-001 | Web-Provider-Tabs (Spotify/Hearthis/Tidal/Netflix/BROWSE) | webplayers.py | WebPlayerTabs (QtWebEngine) | ✓ | ✓ | – | IMPLEMENTING (QtWebEngine via MSVC; MinGW=Stub) |
| WP-002 | Web-Provider-URL-Routing | webproviders.py | webproviders.cpp | ✓ | ✓ | ✓ | VERIFIED |
| WEB-001 | web-casu API endpoints | web_casu.py | Qt HTTP server | ✓ | ✓ (api/version) | ✓ | VERIFIED |
| WEB-002 | Stream proxy (loopback, allow-list) | web_casu + php | native | ✓ | ✓ | ✓ | VERIFIED |
| WEB-003 | Pure web bundling (byte-identical) | pure-web-release | web/pure/ | – | ✓ (SHA) | ✓ | VERIFIED |
| NET-001 | Network streams (http/hls/radio) | mpcasu | Qt network | ✓ | ✓ | ✓ | VERIFIED |
| NET-002 | EPG/XMLTV + M3U parse | casu/epg.py, playlist.py | casu_core | ✓ (M3U/EPG) | – | ✓ | IMPLEMENTING |
| LIB-001 | Library DB (SQLite) | casu/library.py | QtSql/sqlite3 | – | – | – | NOT_TESTED |
| SET-001 | Settings | casu/settings.py | QSettings/JSON | ✓ | – | ✓ | VERIFIED |
| REC-001 | Recording | casu/recording.py | QProcess/FFmpeg | ✓ (arg build) | – | – | IMPLEMENTING |
| CONV-001 | Converter GUI + batch | casu_converter.py | CASU-Converter.exe | ✓ | ✓ (smoke) | ✓ | VERIFIED |
| CONV-002 | CASU import/export, formats | casu/transcode.py | FFmpeg + casu_core | ✓ | ✓ (transcode/export) | ✓ | VERIFIED |
| CLI-001 | CLI parity | casu/cli.py | casu.exe | ✓ | ✓ (golden) | ✓ | VERIFIED |
| PL-001 | Playlist + shuffle/repeat | casu/playlist.py, main_window | Qt model | ✓ (parse) | ✓ | ✓ | VERIFIED |
| UI-001 | Style bible conformance | main_window + webamp ref | Qt stylesheets | – | – | ✓ (smoke) | IMPLEMENTING |
| PKG-001 | Portable ZIP + DLL audit | packaging | CMake/CPack + wine | – | ✓ (clean-prefix) | ✓ | VERIFIED |
| REL-001 | Release gate JSON | release_gate_guard | gate script | – | ✓ (14/14 PASS) | – | VERIFIED |
| INST-001 | setup.exe Installer (NSIS) | – | setup.nsi → MPCASU-Setup.exe | – | ✓ (Wine install/uninstall) | ✓ | VERIFIED |
| INST-002 | Systemweit: casu im PATH + .casu/.mp5-Dateitypen | /usr/bin (Linux) | setup.nsi AddToSystemPath + HKLM Classes | – | ✓ (Wine install) | – | IMPLEMENTING (PATH/Dateityp auf echtem Windows zu verifizieren, BLOCKER-004) |
| CODEC-001 | Media-Foundation/DirectShow-Decoder (CASUNAT2) | mpcasu_native_backend.py | casu_mft.dll (IMFTransform) | – | – | – | NOT_STARTED (geplant, BLOCKER-005) |

Detailed per-feature work packages follow in `roadmap/` (per tool). No feature
may silently disappear; anything not portable is marked BLOCKED with reason.
Rand-Features ohne eigenen Windows-Test sind `IMPLEMENTING`/`NOT_TESTED` —
nie ein falscher PASS.