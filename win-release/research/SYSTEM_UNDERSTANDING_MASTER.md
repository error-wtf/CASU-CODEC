# SYSTEM UNDERSTANDING MASTER

Human-readable synthesis of the entire CASU-CODEC ecosystem, derived from the
frozen reference (`/home/error/Codec-Casu`, HEAD `36df249`), the VLC mechanics
reference, and the Webamp style reference. This is the mental model behind the
Windows port.

## What is CASU?

"Codec for All Segmented Units" — a family of self-verifying media container
formats plus an integrity-first toolchain:
- **CASU sidecar** (legacy): JSON manifest (`MPCASU\0`) + verified source file.
- **CASUNAT1**: header(92B) + JSON manifest + byte-exact original payload,
  SHA-256 verified.
- **CASUNAT2**: native segmented (key-state / tile-update / PCM), decoded
  in-process and in-browser.
- **MP5** (`CASUMP5\0`): zstd-compressed chunk stream + footer manifest
  digest + embedded verified attachment (source).
Everything is bounded and checksummed; errors are typed and surfaced.

## What is MPCASU?

The player product family:
- **MPCASU Desktop** (PySide6 Qt + libVLC): single native player —
  `PlaybackController → Backend (LibVLC/NativeCasu) → VideoSurface`.
- **web-casu** (Python backend + browser frontend `web/`).
- **Pure Web** (frozen, backend-free browser player).
- **CASU Converter** (Tk GUI), **CASU CLI** (`casu/`), **recorder**, EPG/IPTV,
  library, settings.

## Design philosophy

- **One player**: never a second/browser player for desktop playback; YouTube
  enters the normal libVLC pipeline via a transport-only loopback proxy fed by
  one shared resolver (`casu.locations.resolve_media_location`).
- **Integrity first**: every container verified (SHA-256, bounded sizes, no
  path traversal).
- **One product family, one look**: `casu/design.py` tokens are the single
  source; Qt, web and converter mirror them exactly (dark red/black).
- **NOW PLAYING** fixed heading; dynamic title separate; libVLC owns the native
  surface exclusively (no flicker).
- **libVLC does media, MPCASU does the app**; yt-dlp resolves, never plays;
  ffmpeg converts, never plays; web-casu is a separate web product.

## How playback works (desktop)

Local MP4 → stage detect → `LibVLCBackend(surface.handle)` → open → controller
→ play (libVLC draws into VideoSurface). YouTube → shared resolver →
loopback transport (Range/206, refresh on 403) → same LibVLCBackend → same
surface. Native CASU → `NativeCasuBackend` in-process (PCM→audio sink,
frames→video sink). Audio: libVLC for legacy/network; WASAPI/Qt for native CASU
on Windows (PulseAudio is Linux-only).

## How web works

web-casu: browser `web/` → `/api/*` (resolve/search/title/transcode/catalog/
stream-proxy/media) → Python backend → media → browser. Pure web: no backend —
YouTube IFrame API + oEmbed, hls.js, client CASU, optional PHP helpers.

## How converter works

`casu/jobs.py` ConversionEngine: probe (ffprobe) → profile → ffmpeg (or CASU
encode) → progress → result. Batch, CASU import/export, formats.

## Windows differences (what changes vs Linux)

- GUI: Python/PySide → **C++20/Qt6**.
- libVLC: ctypes → **direct C API**, `set_xwindow` → `set_hwnd`.
- Audio: PulseAudio → **WASAPI/Qt**.
- Paths/process/network: pathlib/subprocess/urllib →
  std::filesystem/QProcess/QNetworkAccessManager.
- Packaging: debs → **portable Windows zip** (Qt DLLs + qwindows plugin +
  vlc plugins + ffmpeg/yt-dlp + web/).

## Windows architecture (derived)

Shared C++ libraries (casu_core, casu_codec, casu_media, casu_network,
casu_playback, casu_webapi) + apps (MPCASU.exe, CASU-Converter.exe,
CASU-Web-Backend.exe, casu.exe) + bundled web/pure (byte-identical) +
helpers (ffmpeg.exe/ffprobe.exe/yt-dlp.exe). Cross-compiled with
MinGW-w64 under Linux, verified under Wine.

## Guiding invariants (must never regress)

1. Reference tree is read-only (specification/oracle).
2. Single-player architecture; YouTube = shared resolver + transport + libVLC.
3. Transport is transport, never a player; no full-RAM buffering.
4. Native surface owned by libVLC; no Qt overlay on video.
5. NOW PLAYING fixed heading.
6. Formats integrity-preserved (byte/semantic golden tests).
7. Feature-for-feature, wine-verified; no silent feature loss (BLOCKED not
   deleted); no false PASS.
