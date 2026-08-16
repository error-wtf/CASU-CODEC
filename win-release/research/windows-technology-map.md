# Linux-Specific Inventory + Windows Technology Map

## Linux-specific constructs (grep-based scan of reference)

| # | Reference location | Linux mechanism | Windows replacement | Test |
|---|--------------------|------------------|---------------------|------|
| L1 | mpcasu_native_backend.py | PulseAudio (`PulseAudioSink`) | WASAPI / Qt Multimedia (documented in `windows-audio-design.md`) | Wine audio |
| L2 | mpcasu_backend.py | X11 `libvlc_media_player_set_xwindow(winId)` | `libvlc_media_player_set_hwnd(HWND)` | Wine video |
| L3 | mpcasu_backend.py | `VLC_PLUGIN_PATH` / `/usr/lib/…/vlc/plugins` discovery | bundled `vlc/plugins` + env | clean-prefix run |
| L4 | casu/*, converter | POSIX paths, `/tmp`, `tempfile` | `QStandardPaths`, `std::filesystem`, `%TEMP%` | Unicode/space paths |
| L5 | everywhere | `subprocess.run` (yt-dlp, ffmpeg, ffprobe) | `QProcess` (arg arrays, never shell strings) | Wine helper runs |
| L6 | web_casu.py / php | `urllib`, sockets | `QNetworkAccessManager` / QTcpServer | API tests |
| L7 | main_window | `os`, `signal`, `chmod` where used | Win32/Qt abstractions | build+wine |
| L8 | packaging/build_debs.sh | Bash + dpkg | CMake/CPack (Windows zip) | packaging gate |
| L9 | audio device enumeration | PulseAudio/PyAudio | WASAPI enum / Qt | Wine audio |
| L10 | executable discovery | `shutil.which` | bundled helpers next to exe | clean prefix |

## Windows technology map (per actual usage)

| Python/current | Purpose | Windows (C++20/Qt6) |
|----------------|---------|----------------------|
| PySide6 QWidget | GUI | Qt 6 QWidget |
| ctypes → libVLC | playback | direct libVLC C API |
| PlaybackController | state machine | C++ PlaybackController |
| VideoSurface (winId) | native video | QWidget WA_NativeWindow → HWND |
| urllib | HTTP client | QNetworkAccessManager |
| http.server / threads | web backend / proxy | QTcpServer + sockets (QThread) |
| subprocess | yt-dlp/ffmpeg | QProcess |
| pathlib | paths | QFileInfo/QDir/std::filesystem |
| json | config/data | QJsonDocument / nlohmann-json |
| sqlite3 | library DB | QtSql or sqlite3 |
| zstd (python) | MP5 compression | libzstd (C API) |
| threading | workers | QThread / QtConcurrent / std::thread |
| dataclass/settings | settings | QSettings (portable JSON under app dir) |

## Audio design decision (summary)

Legacy/network media → libVLC (owns audio output on Windows).
Native CASU → dedicated C++ backend with WASAPI (or Qt Multimedia) sink;
no PulseAudio. See `windows-audio-design.md` for the full doc.
