# MPCASU — Acceptance Gate + Feature Matrix + Windows Mapping

## Behavioral compatibility (definition of done)

MPCASU-Windows behaves identically to the Linux reference:
- single player (UI → PlaybackController → Backend → VideoSurface);
- local video/audio, CASU/NAT2/MP5, network streams, YouTube all on the same
  native surface; no browser/second player;
- NOW PLAYING fixed heading; dynamic title separate, never over the surface;
- playlist/library/EPG/settings/recording/visualizer behavior preserved;
- UI look (shared design tokens) preserved; not a redesign;
- clean shutdown, no lingering processes.

## Feature matrix (mpcasu)

| ID | Feature | Reference | Windows | Unit | Wine | Status |
|----|---------|-----------|---------|------|------|--------|
| MPC-001 | App window + single instance | app.py | WP-MPCASU-001/002 | + | + | NOT_STARTED |
| MPC-002 | Sidebar/rail | main_window | WP-010 | + | + | NOT_STARTED |
| MPC-003 | Topbar + NOW PLAYING | main_window | WP-011 | + | + | NOT_STARTED |
| MPC-004 | VideoSurface HWND | videoframe | WP-012 | + | + | NOT_STARTED |
| MPC-005 | Transport/seek/status/cards | main_window | WP-013 | + | + | NOT_STARTED |
| MPC-006 | PlaybackController | mpcasu_playback | WP-020 | + | – | NOT_STARTED |
| MPC-007 | LibVLCBackend | mpcasu_backend | WP-021 | + | + | NOT_STARTED |
| MPC-008 | NativeCasuBackend | mpcasu_native | WP-022 | + | + | NOT_STARTED |
| MPC-009 | Local pipeline | main_window | WP-023 | + | + | NOT_STARTED |
| MPC-010 | Playlist | casu/playlist | WP-030 | + | + | NOT_STARTED |
| MPC-011 | Library | casu/library | WP-031 | + | + | NOT_STARTED |
| MPC-012 | Settings | casu/settings | WP-032 | + | + | NOT_STARTED |
| MPC-013 | EPG/IPTV | casu/epg | WP-033 | + | + | NOT_STARTED |
| MPC-014 | Visualizer+DPI | main_window | WP-034 | + | + | NOT_STARTED |
| MPC-015 | Recording | casu/recording | WP-035 | + | + | NOT_STARTED |
| MPC-016 | YouTube resolve | casu/locations | WP-040 | + | + | NOT_STARTED |
| MPC-017 | YouTube transport | youtube_proxy | WP-041 | + | + (real CDN) | NOT_STARTED |
| MPC-018 | YouTube playback | main_window | WP-042 | + | + (real) | NOT_STARTED |
| MPC-019 | Spotify/providers | casu/spotify | WP-050 | + | + | NOT_STARTED |
| MPC-020 | Input/shortcuts | main_window | WP-051 | + | + | NOT_STARTED |
| MPC-021 | Shutdown/errors/log | main_window | WP-052 | + | + | NOT_STARTED |
| MPC-022 | Packaging + Wine | packaging | WP-060 | – | + (clean prefix) | NOT_STARTED |

## Windows mapping (mpcasu)

| Linux | Windows |
|-------|---------|
| PySide6 QWidget | Qt6 QWidget |
| ctypes→libVLC | direct libVLC C API |
| set_xwindow(winId) | set_hwnd(HWND) |
| PulseAudio | WASAPI/Qt |
| urllib | QNetworkAccessManager |
| http.server proxy | QTcpServer |
| subprocess (yt-dlp/ffmpeg) | QProcess |
| pathlib | QFileInfo/QDir/std::filesystem |
| sqlite3 | QtSql/sqlite3 |
| threading | QThread/QtConcurrent |

## Acceptance gate

PASS requires: build ok, no missing DLLs, unit PASS, Wine matrix PASS
(clean prefix), compatibility (Linux↔Wine) PASS, YouTube real run PASS.
No false PASS.
