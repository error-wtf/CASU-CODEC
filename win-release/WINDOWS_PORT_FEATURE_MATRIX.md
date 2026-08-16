# WINDOWS PORT FEATURE MATRIX

Status: `NOT_STARTED` | `ANALYSIS` | `IMPLEMENTING` | `BUILDING` | `TESTING` |
`WINE_TESTING` | `BLOCKED` | `VERIFIED`

"VERIFIED" requires runtime evidence (Wine GUI/playback, real YouTube/CDN,
golden comparison) — never a mock-only PASS.

| ID | Feature | Reference | Windows target | Unit | Integration | Wine | Status |
|----|---------|-----------|----------------|------|-------------|------|--------|
| CASU-001 | CASU container parse/write | casu/core.py, fileio, schema | casu_core (C++) | – | – | – | NOT_STARTED |
| CASU-002 | Manifest + checksums | casu/schema.py | casu_core | – | – | – | NOT_STARTED |
| CASU-003 | CASUNAT1 decode | casu/native.py | casu_core | – | – | – | NOT_STARTED |
| CASU-004 | CASUNAT2 native | casu/native_v2 | casu_core | – | – | – | NOT_STARTED |
| CASU-005 | MP5 / legacy | casu/mp5 | casu_core | – | – | – | NOT_STARTED |
| CASU-006 | Segments/scheduler/tiles | casu/scheduler, tiles | casu_core | – | – | – | NOT_STARTED |
| CASU-007 | zstd compression | casu (zstd) | casu_core (+zstd) | – | – | – | NOT_STARTED |
| PLAY-001 | Open local media | LibVLCBackend.open_source | LibVLCBackend C++ | – | – | – | NOT_STARTED |
| PLAY-002 | Play/Pause/Resume/Stop | mpcasu_playback.py | PlaybackController | – | – | – | NOT_STARTED |
| PLAY-003 | Seek/duration/position | backend | backend | – | – | – | NOT_STARTED |
| PLAY-004 | Volume/Mute/Rate | backend | backend | – | – | – | NOT_STARTED |
| PLAY-005 | VideoSurface native embed | videoframe.py | QWidget + HWND | – | – | – | NOT_STARTED |
| PLAY-006 | Tracks/subtitles/chapters | backend | backend | – | – | – | NOT_STARTED |
| PLAY-007 | Snapshot | backend | backend | – | – | – | NOT_STARTED |
| PLAY-008 | Fullscreen/DPI/resize | main_window | Qt6 | – | – | – | NOT_STARTED |
| PLAY-009 | Native CASU playback | mpcasu_native_backend | NativeCasuBackend | – | – | – | NOT_STARTED |
| PLAY-010 | Visualizer | main_window | Qt/audio | – | – | – | NOT_STARTED |
| YT-001 | yt-dlp resolve (QProcess) | casu/locations.py | yt-dlp.exe + QProcess | – | – | – | NOT_STARTED |
| YT-002 | Loopback transport (Range/206) | youtube_proxy.py | QTcpServer/QNAM | – | – | – | NOT_STARTED |
| YT-003 | YouTube playback via libVLC | main_window | LibVLCBackend | – | – | – | NOT_STARTED |
| WEB-001 | web-casu API endpoints | web_casu.py | Qt HTTP server | – | – | – | NOT_STARTED |
| WEB-002 | Stream proxy (loopback, allow-list) | web_casu + php | native | – | – | – | NOT_STARTED |
| WEB-003 | Pure web bundling (byte-identical) | pure-web-release | web/pure/ | – | – | – | NOT_STARTED |
| NET-001 | Network streams (http/hls/radio) | mpcasu | Qt network | – | – | – | NOT_STARTED |
| NET-002 | EPG/XMLTV + M3U parse | casu/epg.py, playlist.py | casu_core | – | – | – | NOT_STARTED |
| LIB-001 | Library DB (SQLite) | casu/library.py | QtSql/sqlite3 | – | – | – | NOT_STARTED |
| SET-001 | Settings | casu/settings.py | QSettings/JSON | – | – | – | NOT_STARTED |
| REC-001 | Recording | casu/recording.py | QProcess/FFmpeg | – | – | – | NOT_STARTED |
| CONV-001 | Converter GUI + batch | casu_converter.py | CASU-Converter.exe | – | – | – | NOT_STARTED |
| CONV-002 | CASU import/export, formats | casu/transcode.py | FFmpeg + casu_core | – | – | – | NOT_STARTED |
| CLI-001 | CLI parity | casu/cli.py | casu.exe | – | – | – | NOT_STARTED |
| PL-001 | Playlist + shuffle/repeat | casu/playlist.py, main_window | Qt model | – | – | – | NOT_STARTED |
| UI-001 | Style bible conformance | main_window + webamp ref | Qt stylesheets | – | – | – | NOT_STARTED |
| PKG-001 | Portable ZIP + DLL audit | packaging | CMake/CPack + wine | – | – | – | NOT_STARTED |
| REL-001 | Release gate JSON | release_gate_guard | gate script | – | – | – | NOT_STARTED |

Detailed per-feature work packages follow in `roadmap/` (per tool). No feature
may silently disappear; anything not portable is marked BLOCKED with reason.
