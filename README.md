# CASU & MPCASU — Segmented-State Media Codec & Player

CASU (Codec for All Segmented Units) is a standalone segmented media container. MPCASU is the accompanying desktop and web media player. The project also includes a bidirectional batch converter and CLI tools.

> **Status:** `1.0.0-rc8` — Release Candidate. Current gate status is at [RELEASE_GATE_STATUS.json](RELEASE_GATE_STATUS.json).

---

## Components

| Component | Role | Launch |
|---|---|---|
| **CASU Codec** | Analyze, produce CASUNAT1/CASUNAT2, verify, and export | `casu` module / `casu` CLI |
| **CASU Converter** | Single-file, multi-file, and recursive folder conversion | `casu-converter` |
| **MPCASU Desktop** | Play CASU and any media/stream supported by installed libVLC | `mpcasu` |
| **MPCASU Web** | Local media, streams, YouTube, and CASU in the browser | `web/index.html` / `web-casu` |

CASUNAT2 stores reconstructable video key states, tile changes, time-stamped PCM, text/bitmap subtitles, chapters, metadata, and attachments. The original source file is **not** required for native playback.

---

## Debian Package Installation

```bash
./packaging/build_debs.sh
cd dist
sha256sum -c SHA256SUMS
sudo dpkg -i casu-codec_1.0.0-rc8_all.deb \
  casu-converter_1.0.0-rc8_all.deb \
  mpcasu_1.0.0-rc8_all.deb
sudo dpkg -i web-casu_1.0.0-rc8_all.deb
```

If Debian reports missing dependencies:

```bash
sudo apt-get -f install
```

The packages install:

- `/usr/bin/casu`, `/usr/bin/casu-converter`, `/usr/bin/mpcasu`, `/usr/bin/web-casu`
- Desktop entries and icons
- Documentation and web player under `/usr/share/casu-codec/`

---

## Quick Start

### Desktop Player

```bash
mpcasu                          # Launch the player GUI
mpcasu /path/to/video.mp4       # Play a local file
mpcasu /path/to/file.casu       # Play a CASU container
```

**Controls:**
| Key | Action |
|---|---|
| `Space` | Play / Pause |
| `F` | Fullscreen |
| `M` | Mute |
| `S` | Stop |
| `P` | Previous track |
| `←` / `→` | Seek -10 / +10 seconds |
| `↑` / `↓` | Volume +5 / -5 |
| `Ctrl+O` | Open file |
| `Ctrl+L` | Open network URL |
| `Ctrl+I` | Media information |
| `Ctrl+T` | Go to time |
| `Ctrl+Q` | Quit |
| `Esc` | Leave fullscreen |

The playback route is selected automatically by content inspection:
- **CASUNAT2** → Native segment decoder (key-state/tile/PCM)
- **CASUNAT1** + valid **sidecars** → Verified compatibility path via libVLC
- All other audio/video files → libVLC in-process

Content detection works even with missing or misleading file extensions. A `.casu` file is accepted as ordinary media only if the bounded probe actually reports an audio or video stream.

**Extended features:**
- Extended-M3U / XMLTV EPG with now/next programme display
- YouTube and Spotify playback via yt-dlp behind an explicit legal-consent gate
  (personal use only; resolved URLs are never stored or redistributed)
- Options dialog: volume, resume-playback toggle, visualizer mode
  (spectrum / waveform / both / off), yt-dlp cache management, media database
  refresh, and legal consent management
- Queue entries carry format badges (`[MP3]`, `[MP4]`, `[CASU]`, `[STREAM]`,
  `[YT]`, `[RTSP]`, …) detected from real entry content
- Session restore: playlist, playback position (when resume is enabled), and
  window geometry survive restarts
- DVD / CD / camera / screen / audio capture sources
- Verified stream recording (MKV, MP4, TS, WebM, OGG, MP3, FLAC, WAV)
- Folder import, shuffle, repeat, A–B loop, bookmarks
- Title / chapter / audio / video / subtitle track selection
- External subtitle loading (SRT, ASS, SSA, VTT, SUB)
- Frame-by-frame stepping, PNG snapshot
- Aspect ratio, crop, zoom, deinterlacing
- Stereo channel modes, libVLC equalizer presets
- Audio / subtitle synchronization (-5s to +5s)
- Dynamic audio output device selection

### Converter

```bash
casu-converter                  # Launch the converter GUI
```

**Modes:**

| Mode | Description |
|---|---|
| `media-to-media` | Convert any FFmpeg-decodable format to another (default) |
| `to-casu` | Encode media into CASU (sidecar or native CASUNAT2) |
| `from-casu` | Reconstruct CASU back to standard media |

All three modes support **single files**, **multi-selection**, and **recursive folders**. Subdirectories are preserved.

**Profiles:** `remux`, `balanced`, `high`, `small`, `lossless`

**Configurable:** Tile size (8–1024 px), key-state interval (0.1–3600 s), video codec, audio codec, subtitle mode, all tracks, metadata/chapter preservation.

Batch reports include source/output hashes, profile hash, frame/key/tile/hold/audio/subtitle counters, runtime, verification, and warnings. Reports are exportable as CSV or Markdown.

### CLI

```bash
# Standalone native CASUNAT2
casu pack-v2 input.mkv --output output.casu

# General convert
casu convert input.mp4 --container native-v2 --output output.casu

# Complete folder with resume and retry
casu convert media-folder --container native-v2 \
  --output casu-folder --retry 1 --resume

# Verify and inspect
casu verify output.casu
casu info output.casu

# Back to standard media
casu export output.casu --output restored.mp4
casu export album.casu --output restored.flac

# Direct transcode
casu transcode input.avi --output output.mp4 --preset high
casu transcode album/ --output opus/ --format opus --preset balanced --resume

# Remux without re-encoding
casu transcode input.mkv --output copy.mkv --preset remux

# Recover damaged prefix
casu repair-v2 damaged.casu --output recovered.casu
```

---

## Web Player

```bash
web-casu                        # Launch (binds to 127.0.0.1, opens browser)
web-casu --port 8080            # Custom port
web-casu --no-browser           # Headless server
web-casu --check                # Verify assets and exit
```

From the repository:

```bash
cd /home/error/Lino-Codec
python3 web_casu.py --port 8080
# Open http://localhost:8080/web/
```

**Features:**
- Local audio/video files and drag-and-drop
- Automatic FFmpeg fallback for browser-unsupported formats (adaptive WebM/MP4)
- Direct media streams and YouTube embedding (iframe-based, controllable from main transport)
- M3U / M3U8 / PLS / XMLTV with searchable Live TV EPG and now/next
- Playlist search, sort, shuffle, repeat, A–B loop, speed control
- SRT / WebVTT subtitles for local media
- CASU sidecar and CASUNAT1 SHA-256 verification
- Native CASUNAT2 key/tile/PCM playback with automatic CASU→MP4/WebM fallback
- Selectable CASUNAT2 video, audio, and subtitle tracks
- CASUNAT2 text/bitmap subtitles and chapter selection
- Fullscreen, PNG snapshot, browser Picture-in-Picture

**Security:** Rejects foreign Host/Origin headers. Serves CSP, frame-ancestors, referrer, and permissions-policy headers.

---

## Test Suite

Each run is capped at 60 seconds:

```bash
# Fast tests
timeout 60s pytest -q -m 'not media'

# Codec, export, web
timeout 60s pytest -q \
  tests/test_strict_acceptance.py \
  tests/test_native_v2_acceptance.py \
  tests/test_export.py \
  tests/test_web_player.py

# Native playback
timeout 60s pytest -q tests/test_native_player_backend.py

# Desktop GUI (requires xvfb)
timeout 60s xvfb-run -a pytest -q \
  tests/test_player_ui.py tests/test_converter_ui.py

# libVLC runtime
timeout 60s pytest -q tests/test_libvlc_runtime.py

# JavaScript
node --check web/app.js
node --check web/casu-native.js
```

---

## Architecture

```text
Normal media ── libVLC ──────────────────┐
HTTP/HLS/RTSP/YouTube ─ libVLC/yt-dlp ───┼─ MPCASU Desktop
CASUNAT2 ─ NativeCasuBackend ────────────┘

Media ─ FFmpeg/PyAV ─ CASUNAT2 ─ CASU Reader/Player/Exporter
```

| Module | Purpose |
|---|---|
| `casu/strict/` | Source-resolution, plane-aware, PTS-exact analysis |
| `casu/native_v2/` | Container, reader/writer, seek, integrity, recovery |
| `casu/jobs.py` | Atomic batch engine with resume, cancel, reports |
| `mpcasu_backend.py` | libVLC compatibility backend |
| `mpcasu_native_backend.py` | Standalone native CASU playback |
| `web/` | Browser-based MPCASU player |

---

## Real-World Limitations

- Legacy format support depends on installed VLC/FFmpeg modules — no artificial whitelist.
- Bitmap subtitles play natively and burn into video during export; PGS/DVD/DVB/XSub cannot remux into every target container.
- The web player offers native multi-track and bitmap rendering. ASS/libass typography is preserved on desktop; browser uses text fallback.
- Physical audio hardware, Windows/macOS packages, and long-duration power measurement require separate platform tests.

---

## Further Reading

- [CASU Format Specification](CASU_FORMAT_SPECIFICATION.md)
- [Converter Documentation](docs/CASU_CONVERTER.md)
- [Implementation Report](IMPLEMENTATION_REPORT.md)
- [Test Report](TEST_REPORT.md)
- [MPCASU Feature Matrix](MPCASU_FEATURE_COMPLETION_MATRIX.md)
- [60-Step Roadmap](ROADMAP_60_STEPS.md)
- [Licenses & Third-Party Components](THIRD_PARTY_COMPONENTS.md)

**License:** Anti-Capitalist License 1.4 / All Rights Reserved, Lino Casu.
Third-party components retain their respective licenses.
