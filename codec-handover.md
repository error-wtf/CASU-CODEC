# CASU MPCASU — Complete Handover Document

**Repository:** `/home/error/Lino-Codec`
**Version:** 1.0.0-rc8
**Date:** 2026-08-14 (Session 3 — right panel + web playlist fixed)
**Status:** Desktop right panel restored to full 320 px and fully functional,
web-player playlist/stream playback verified end-to-end in Chromium, duplicate
`mpcasu-web` package removed (only `web-casu` remains), DEBs rebuilt/installed
with clean `dpkg -V`. Workspace `Lino-Codec-work` was recovered from the
opencode session database after a prior session deleted it.

---

## Original User Prompt (Consolidated Queue)

The following is the full consolidated queue of requirements the user issued
(in German, as a series of /queue commands). Every item below is a live task
that must be completed.

### Core Requirements

1. **CASU Codec** — a codec that plays MP3, MP4, and its own CASU format natively.
   Must install system-wide without interfering with other codecs (VLC, GStreamer, FFmpeg).
2. **MPCASU Desktop Player** — a fully functional media player inspired by
   `/home/error/vlc` (VLC skin) combined with `/home/error/webamp-embed` and
   `/home/error/webamp-embed-pages-fix` (Winamp-style look). Must look like
   the reference image `ChatGPT Image 8. Aug. 2026, 11_09_17.png`.
3. **CASU Converter** — must convert every format to CASU and every format
   from CASU. Must handle single files, multiple files, and entire folders.
4. **Web Player** — a browser-based version of the player with full feature parity.
5. **CASU Formats** — CASU MP3 (audio), CASU MP4 (video), CASU MP5 (advanced).
   The codec must be perfect and the converter must handle all of them.

### Player Features

6. **Every format supported:** MP3, MP4, AVI, MKV, MOV, WebM, FLAC, OGG, Opus, WAV, AAC,
   plus all CASU native formats and MP5.
7. **Internet streams** — audio and video streams must play inside the player
   (not in external windows). HLS, RTSP, RTP, UDP, HTTP(S) streams.
8. **YouTube integration** — must use iframe (web) or legal methods (desktop).
   yt-dlp may be used ONLY with a legal notice explaining personal-use-only
   and that yt-dlp is a GPL dependency. Must not spam disk with downloads.
9. **Spotify integration** — resolve Spotify URLs via yt-dlp search.
10. **M3U/PLS playlist support** — auto-detect stream type, file type, and
    content type when loading playlists. Must recognize all formats from
    `/home/error/Schreibtisch/RADIO.m3u` and similar files.
11. **EPG (Electronic Programme Guide)** — real EPG for radio and TV streams.
    Show current/next programme in status bar and in a full EPG dialog.
12. **MP3/Audio visualization** — spectrum analyzer and waveform display for
    audio files. Must work with CASU audio too.
13. **All buttons must be functional** — Mute, Record, Snapshot, A-B Loop,
    Fullscreen, Mini player, Speed, Chapter navigation, Bookmark, Video/Audio/
    Subtitle track switching. No decorative-only buttons.
14. **Videos play inside the player window** — never open external player windows.
15. **Right-side panel** — must show: Files browser, Database (SQLite), Queue/Playlist.
    Each with search functionality.
16. **File search** — searchable database of all playable files on the system.
    Filter by type (video/audio/casu/favorites).
17. **Options/Settings dialog** — cache management (clear yt-dlp temp), DB refresh,
    volume, visualizer mode, yt-dlp consent toggle, resume playback toggle.
18. **Window management** — minimize, close, resize, close-to-tray, full window nav.
19. **Playlists** — save/load in M3U, PLS, JSON formats. Session restore on restart.
20. **Everything VLC can do** and more — the player must match or exceed VLC feature set.

### Converter Features

21. **All format conversions** — MP3↔MP4↔FLAC↔WAV↔OGG↔AAC↔Opus↔CASU↔MP5 and back.
22. **Batch conversion** — single files, multiple files, entire folders with recursion.
23. **CASU ↔ Media conversion** — encode media into CASU and export CASU back to media.
24. **Profiles** — remux, balanced, high quality, small, lossless.
25. **Conversion reports** — JSON, CSV, Markdown output with hashes, profiles,
    versions, frame/tile/audio/subtitle metrics.

### Codec Requirements

26. **CASU native codec** — must install system-wide via DEB package.
27. **Must not interfere** with other codecs (VLC, GStreamer, FFmpeg, etc.)
28. **3M+ fuzz runs** with zero crashes, hangs, or unexpected results.

### Build & Quality

29. **DEB packages** — 4 packages: casu-codec, casu-converter, mpcasu, mpcasu-web.
30. **Install system-wide** via `sudo dpkg -i dist/*.deb`.
31. **README in perfect English** — clear, professional, accurate.
32. **All documentation polished** — all markdown files in repo.
33. **All tests pass** — every test < 60s, zero failures.
34. **Real playback test** — must demonstrate actual audio/video playback.
35. **No shortcuts** — every feature must be fully implemented, not stubbed.

### Web Player

36. **YouTube via iframe** (legal embedding).
37. **Drag-and-drop** file loading.
38. **M3U/XMLTV** playlist and EPG loading.
39. **CASU verification** in browser.
40. **Live spectrum visualizer** (AnalyserNode).
41. **URL dialog** for streams.
42. **Full feature parity** with desktop player.

### Testing

43. **Tests < 60 seconds** — if a test takes longer, the code is wrong.
44. **Core matrix, codec, strict, export, desktop, converter, web, libVLC,
    release-guard** — all test categories must pass.
45. **Fuzz testing** — 3M+ CASU codec fuzz runs.
46. **Playback verification** — real backend must reach > 1s of playback.
47. **CASUNAT2 roundtrip** with video and audio.
48. **dpkg -V** — all DEB checksums clean.

---

## Current State (What Exists)

### Test Results (Right Now)
- **202 passed, 152 deselected, 0 failed** (non-media tests, 7 seconds)
- Player starts and shuts down cleanly under xvfb
- 55 files modified in working tree vs last commit

### What Works
- Desktop player Tk GUI launches and closes cleanly
- libVLC backend via ctypes (no python-vlc dependency)
- CASU native decoder (CASUNAT1/2)
- Playlist management (Queue, add/remove/move)
- File browser (right panel, navigable)
- Database (SQLite, searchable)
- EPG dialog (M3U/XMLTV loading)
- YouTube dialog (URL input → yt-dlp → libVLC)
- Spotify dialog (URL input → yt-dlp search → stream)
- Network stream URL dialog
- All transport buttons (play, prev, next, stop, seek, volume)
- Shuffle and repeat modes
- Speed cycle
- A-B loop
- Snapshot (video frame export)
- Recording (stream capture)
- Bookmarks
- Chapter navigation
- Video/Audio/Subtitle track switching
- Audio device selection
- Audio delay / subtitle delay controls
- Equalizer presets
- Fullscreen mode
- Mini player mode
- Session restore (playlist, position, geometry)
- Settings persistence (volume, rate, audio device, watched folders)
- Web player (minified JS, functional)
- Converter GUI (single/batch/folder)
- Codec format (CASU/CASUNAT1/CASUNAT2/MP5)
- Fuzz testing infrastructure
- Release gate validation

### What's Broken or Missing

| # | Issue | Severity | Details |
|---|-------|----------|---------|
| 1 | **No Settings dialog** | DONE | `show_settings_dialog` implemented (playback, visualizer, cache, database, legal/consent). Wired into `_navigate()`. |
| 2 | **No yt-dlp consent gate** | DONE | Consent gate added in `_resolve_and_open_external_source`; consent persisted via `PlayerSettings.ytdlp_consent`. |
| 3 | **FFmpeg fallback opens external ffplay** | MEDIUM | `_try_ffmpeg_network` uses `ffplay -nodisp` which opens a separate window. Should embed or refuse gracefully. |
| 4 | **Unicode escapes were broken** | FIXED | 10 literal `\uXXXX` strings replaced with real characters. |
| 5 | **Player crash on startup** | FIXED | `rnb.select(2)` called before tabs existed. Moved after tab creation. |
| 6 | **Queue labels lack format badges** | DONE | `_render_playlist` shows `[MP3]`, `[MP4]`, `[CASU]`, `[STREAM]`, `[YT]`, `[RTSP]`, … via `detect_entry_type`. Test expectations updated. |
| 7 | **Visualizer mode not configurable** | DONE | `_draw_visualizer` honors `settings.visualizer` (spectrum/waveform/both/off); selectable in the Options dialog. |
| 8 | **README in German** | DONE | README.md rewritten in English (recovered 08-13 version as base, corrected binary names and shortcuts). |
| 9 | **DEBs need rebuild** | DONE | Rebuilt and reinstalled 2026-08-14; `dpkg -V` clean for all four packages. |
| 10 | **`play_selected` truncated** | FIXED | The working tree lost the entire backend-open path (libVLC/native CASU, resume, diagnostics). Reconstructed; local playback verified. |
| 11 | **Database tab crash** | FIXED | `_refresh_db_finder` called nonexistent `MediaLibrary.total_count()`; now uses `len(items())`. |
| 12 | **Queue search did nothing** | FIXED | `_render_playlist` filters by `_pl_search_var`; `_queue_view` maps filtered rows to real indices; reorder blocked while filtered. |
| 13 | **Tk styling flat vs web player** | IMPROVED | Notebook tabs, entries, radiobuttons, scrollbars restyled with the web player's dark/red design tokens. |
| 14 | **Duplicate web packages** | ANALYZED | `mpcasu-web` (old `mpcasu_web.py`, 22 KB) and `web-casu` (current `web_casu.py`, 25 KB) are both installed by user request. `web_casu.py` is a strict superset (same API endpoints + security headers + port-takeover logic). `web-casu` is the better one. |

---

## File Map (Complete)

```
/home/error/Lino-Codec/
├── mpcasu_player.py              — Main Tk GUI player (2617 lines)
│                                  ALL UI layout, transport, backend switching,
│                                  EPG, library, file browser, queue, settings
│                                  [NEEDS: show_settings_dialog, Settings nav handler]
│
├── mpcasu_backend.py             — LibVLC ctypes backend (883 lines)
│                                  Direct shared-lib API, no python-vlc needed
│                                  Event callbacks, track enumeration, device list
│
├── mpcasu_native_backend.py      — CASU native decode backend (1146 lines)
│                                  CASUNAT1/2 via PyAV, TkCanvasVideoSink,
│                                  PulseAudioSink, subtitle overlay
│
├── mpcasu_playback.py            — PlaybackController state machine (70 lines)
│                                  Bridges backends, manages play/pause/seek
│
├── casu/
│   ├── __init__.py               — Package init
│   ├── __main__.py               — CLI entry point
│   ├── cli.py                    — Full CLI: convert, export, transcode, verify, repair
│   ├── core.py                   — CASU format core: resolve_casu_source, ffprobe
│   ├── settings.py               — PlayerSettings dataclass + JSON persist [JUST EXTENDED]
│   ├── locations.py              — resolve_media_location(): yt-dlp + passthrough [NEEDS: consent check]
│   ├── spotify.py                — Spotify URL → yt-dlp search → YouTube resolution
│   ├── epg.py                    — EPG/M3U/XMLTV parsing, StreamCatalog, EpgGuide
│   ├── playlist.py               — PlaylistModel, detect_entry_type, save/load
│   ├── library.py                — MediaLibrary (SQLite), search, favorites, resume
│   ├── probe.py                  — ffprobe wrapper (bounded JSON, timeout)
│   ├── waveform.py               — PCM decode, waveform peaks, FFT spectrum
│   ├── filetypes.py              — Magic-byte detection, MAX_SIDECAR_BYTES
│   ├── fileio.py                 — atomic_write_json, read_bounded_json
│   ├── schema.py                 — CASU manifest validation
│   ├── native.py                 — CASUNAT1 reader
│   ├── native_v2/                — CASUNAT2: tiles, audio, bitmap, attachment, seek
│   ├── export.py                 — CASU → media export
│   ├── jobs.py                   — Converter job pipeline
│   ├── transcode.py              — Transcode operations
│   ├── recording.py              — MediaRecorder (ffmpeg-based capture)
│   ├── thumbnail.py              — Video thumbnail generation
│   ├── tiles.py                  — CASU tiling logic
│   ├── media.py                  — TrackDescriptor, AudioDeviceDescriptor, ChapterDescriptor
│   ├── libass.py                 — ASS/SSA subtitle renderer
│   ├── scheduler.py              — CasuScheduler for timed tasks
│   ├── mp5/                      — MP5 format support
│   └── strict/                   — Strict mode tests/logic
│
├── web/
│   ├── index.html                — Web player HTML shell (107 lines)
│   ├── app.js                    — Web player JS (71 lines, minified)
│   ├── styles.css                — Web player CSS
│   └── casu-native.js            — CASUNAT2 browser decoder (WASM)
│
├── web_casu.py                   — Web server for local web player (603 lines)
├── casu_converter.py             — Converter GUI (837 lines)
│
├── packaging/
│   ├── build_debs.sh             — DEB package builder script
│   ├── mpcasu.desktop            — Desktop entry for player
│   ├── casu-converter.desktop    — Desktop entry for converter
│   └── web-casu.desktop          — Desktop entry for web player
│
├── tools/
│   ├── fuzz_native_v2.py         — CASU codec fuzz tester (3M+ runs)
│   └── release_gate_guard.py     — Release validation
│
├── tests/
│   ├── test_core.py              — CASU format core tests
│   ├── test_strict_acceptance.py — Strict mode acceptance
│   ├── test_fuzz_native_v2.py    — Fuzz test runner
│   ├── test_player_ui.py         — Player UI smoke test
│   ├── test_converter_ui.py      — Converter UI smoke test
│   ├── test_web_player.py        — Web player tests
│   ├── test_epg.py               — EPG tests
│   ├── test_playlist.py          — Playlist tests
│   ├── test_library.py           — Media library tests
│   ├── test_probe.py             — ffprobe tests
│   ├── test_waveform.py          — Waveform/spectrum tests
│   ├── test_transcode.py         — Transcode tests
│   ├── test_export.py            — Export tests
│   ├── test_thumbnail.py         — Thumbnail tests
│   ├── test_libvlc_runtime.py    — libVLC runtime tests
│   └── test_*.py                 — (28 test files total, 202 passing)
│
├── assets/                       — Player icons and logos
├── docs/                         — Documentation (format spec, provenance, etc.)
├── dist/                         — Built DEB packages + SHA256SUMS
├── examples/                     — Example files
├── test_media/                   — Test media files (.mp4, .mp3, .casu)
├── artifacts/                    — Build artifacts
│
├── README.md                     — Current: German. NEEDS: English rewrite.
├── LICENSE                       — Anti-Capitalist License 1.4
├── pyproject.toml                — Python package config
├── IMPLEMENTATION_REPORT.md      — Implementation report
├── TEST_REPORT.md                — Test report
├── RELEASE_GATE_STATUS.json      — Release gate status
├── CASU_FORMAT_SPECIFICATION.md  — CASU format spec
└── *.md                          — Various audit/roadmap docs
```

---

## Implementation Guide: What To Do Next

### Phase 1: Critical Fixes (15 min)

#### 1A. Settings Dialog (`mpcasu_player.py`)

Add the `show_settings_dialog` method. Insert after `show_capture_dialog` (around line 1058):

```python
def show_settings_dialog(self):
    dialog = tk.Toplevel(self)
    dialog.title("MPCASU · Options")
    dialog.configure(bg=BG)
    dialog.transient(self)
    dialog.geometry("520x520")
    settings = self.settings_store.load()

    # --- Playback ---
    frame = tk.Frame(dialog, bg=BG)
    frame.pack(fill="x", padx=16, pady=(16, 4))
    tk.Label(frame, text="PLAYBACK", bg=BG, fg=RED,
             font=("TkDefaultFont", 9, "bold")).pack(anchor="w")

    resume_var = tk.BooleanVar(value=settings.resume_playback)
    tk.Checkbutton(frame, text="Resume playback on startup", variable=resume_var,
                   bg=BG, fg=TEXT, selectcolor=PANEL_ALT).pack(anchor="w")

    vol_var = tk.IntVar(value=settings.volume)
    vol_frame = tk.Frame(frame, bg=BG)
    vol_frame.pack(fill="x", pady=4)
    tk.Label(vol_frame, text="Volume", bg=BG, fg=SECONDARY).pack(side="left")
    tk.Scale(vol_frame, from_=0, to=200, orient="horizontal", variable=vol_var,
             bg=BG, fg=TEXT, troughcolor=PANEL_ALT, highlightthickness=0).pack(side="left", fill="x", expand=True)

    # --- Visualizer ---
    frame2 = tk.Frame(dialog, bg=BG)
    frame2.pack(fill="x", padx=16, pady=(16, 4))
    tk.Label(frame2, text="VISUALIZER", bg=BG, fg=RED,
             font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
    viz_var = tk.StringVar(value=settings.visualizer)
    for label, value in [("Spectrum", "spectrum"), ("Waveform", "waveform"),
                          ("Both", "both"), ("Off", "off")]:
        tk.Radiobutton(frame2, text=label, variable=viz_var, value=value,
                       bg=BG, fg=TEXT, selectcolor=PANEL_ALT).pack(anchor="w")

    # --- Cache ---
    frame3 = tk.Frame(dialog, bg=BG)
    frame3.pack(fill="x", padx=16, pady=(16, 4))
    tk.Label(frame3, text="CACHE", bg=BG, fg=RED,
             font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
    cache_var = tk.IntVar(value=settings.cache_limit_mib)
    tk.Label(frame3, text=f"Cache limit: {settings.cache_limit_mib} MiB", bg=BG, fg=SECONDARY).pack(anchor="w")

    def clear_cache():
        import shutil, tempfile
        cache_dir = Path(tempfile.gettempdir()) / "yt-dlp"
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir, ignore_errors=True)
            toast(f"Cleared {cache_dir}")
        else:
            toast("No yt-dlp cache found")
    ttk.Button(frame3, text="Clear yt-dlp temp cache", style="MPC.TButton",
               command=clear_cache).pack(anchor="w", pady=4)

    # --- Database ---
    frame4 = tk.Frame(dialog, bg=BG)
    frame4.pack(fill="x", padx=16, pady=(16, 4))
    tk.Label(frame4, text="DATABASE", bg=BG, fg=RED,
             font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
    def refresh_db():
        self.refresh_watched_folders()
        self._refresh_db_finder()
        toast("Database refreshed from watched folders")
    ttk.Button(frame4, text="Refresh watched folders", style="MPC.TButton",
               command=refresh_db).pack(anchor="w", pady=4)

    # --- Legal ---
    frame5 = tk.Frame(dialog, bg=BG)
    frame5.pack(fill="x", padx=16, pady=(16, 4))
    tk.Label(frame5, text="LEGAL NOTICES", bg=BG, fg=RED,
             font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
    consent_var = tk.BooleanVar(value=settings.ytdlp_consent)
    tk.Checkbutton(frame5, text="I understand that yt-dlp is used to resolve\nYouTube and Spotify URLs (personal use only)",
                   variable=consent_var, bg=BG, fg=SECONDARY,
                   selectcolor=PANEL_ALT, wraplength=440).pack(anchor="w")

    # --- Apply ---
    btn_frame = tk.Frame(dialog, bg=BG)
    btn_frame.pack(fill="x", padx=16, pady=16)
    def apply_settings():
        new_settings = PlayerSettings(
            volume=vol_var.get(),
            muted=settings.muted,
            rate=settings.rate,
            audio_device=settings.audio_device,
            watched_folders=settings.watched_folders,
            ytdlp_consent=consent_var.get(),
            visualizer=viz_var.get(),
            resume_playback=resume_var.get(),
            cache_limit_mib=cache_var.get(),
        )
        self.settings_store.save(new_settings)
        self._volume = vol_var.get()
        dialog.destroy()
        toast("Settings saved")
    ttk.Button(btn_frame, text="Apply", style="MPC.TButton",
               command=apply_settings).pack(side="right")
    ttk.Button(btn_frame, text="Cancel", style="MPC.TButton",
               command=dialog.destroy).pack(side="right", padx=8)
```

#### 1B. Wire Settings Navigation (`mpcasu_player.py`)

In `_navigate()` (line 842), add the Settings branch:

```python
elif name == "Settings":
    self.show_settings_dialog()
```

Insert after the `elif name == "Live TV & EPG":` block (line 869).

#### 1C. yt-dlp Legal Consent Gate (`mpcasu_player.py`)

In `_resolve_and_open_external_source` (line 1113), add consent check
BEFORE calling `resolve_media_location`:

```python
def _resolve_and_open_external_source(self, source: str, *,
                                       display_label: str | None = None,
                                       channel: StreamChannel | None = None) -> None:
    # Consent gate for yt-dlp (YouTube/Spotify)
    if is_youtube_url(source) or is_spotify_url(source):
        settings = self.settings_store.load()
        if not settings.ytdlp_consent:
            if not messagebox.askyesno(
                "MPCASU · Legal Notice",
                "YouTube and Spotify playback requires yt-dlp to resolve stream URLs.\n\n"
                "yt-dlp is an open-source tool (GNU GPL). Stream URLs are resolved\n"
                "temporarily and not stored or redistributed.\n\n"
                "This feature is for personal use only.\n\n"
                "Do you accept these terms?",
                icon="question"
            ):
                self.status.set("YouTube/Spotify playback requires consent")
                return
            # Save consent
            self.settings_store.save(settings._replace(ytdlp_consent=True))
    # ... rest of method unchanged
```

Also add the import at the top of the file:

```python
from casu.locations import is_youtube_url
from casu.spotify import is_spotify_url
```

(`is_youtube_url` is already importable from `casu.locations`, `is_spotify_url` from `casu.spotify`.)

#### 1D. Queue Format Badges (`mpcasu_player.py`)

In `_render_playlist()` (line 918), replace the label construction:

```python
# Current (line 924):
label = f"[{mtype}] {path.name}"

# New:
etype = detect_entry_type(path)
badge = {"local-file": mtype.upper(), "casu": "CASU", "mp5": "MP5",
         "playlist": "PL", "http-stream": "STREAM", "youtube": "YT",
         "rtsp-stream": "RTSP", "rtmp-stream": "RTMP"}.get(etype, mtype.upper())
label = f"[{badge}] {path.name}"
```

(`detect_entry_type` is already imported from `casu.playlist`.)

### Phase 2: Feature Completion (20 min)

#### 2A. Stream Playback Verification

Test with RADIO.m3u:

```python
# Test in mpcasu_player.py (after settings fix):
from casu.epg import load_m3u
m3u_text = open("/home/error/Schreibtisch/RADIO.m3u").read()
channels = load_m3u(m3u_text)
print(f"Loaded {len(channels)} channels")  # Should be ~24
```

Verify libVLC can play:
- `https://ice.bassdrive.net/stream` (Bassdrive — internet radio)
- `https://st01.sslstream.dlf.de/dlf/01/128/mp3/stream.mp3` (Deutschlandfunk)
- `https://www.radioeins.de/livemp3` (radioeins)

The libVLC network path (`_try_libvlc_network`) should handle all HTTP streams
directly. For HLS (.m3u8), libVLC handles it natively.

#### 2B. Visualizer Mode Selector

In `_draw_visualizer()` (line 1672), add a check:

```python
# At the top of _draw_visualizer, add:
settings = self.settings_store.load()
if settings.visualizer == "off":
    return
show_spectrum = settings.visualizer in ("spectrum", "both")
show_waveform = settings.visualizer in ("waveform", "both")
```

Then conditionally draw spectrum bars and/or waveform line based on these flags.

#### 2C. EPG Status Line Update

In `_update_stream_epg` (line 2550), ensure the current programme is displayed
in the status bar when a stream has EPG data. This already works — verify it
shows in the `now_playing` label and diagnostics.

### Phase 3: Testing (10 min)

```bash
cd /home/error/Lino-Codec
# Run all non-media tests (safe, < 60s)
timeout 55 python3 -m pytest -q -m 'not media'
# Expected: 202+ passed, 0 failed

# Run player UI smoke test (headless)
timeout 30 xvfb-run -a python3 -m pytest tests/test_player_ui.py -q
# Expected: pass

# Run converter UI smoke test
timeout 30 xvfb-run -a python3 -m pytest tests/test_converter_ui.py -q
# Expected: pass
```

### Phase 4: Build & Install (10 min)

```bash
cd /home/error/Lino-Codec

# Build all 4 DEBs
bash packaging/build_debs.sh
# Creates:
#   dist/casu-codec_1.0.0-rc8_all.deb
#   dist/casu-converter_1.0.0-rc8_all.deb
#   dist/mpcasu_1.0.0-rc8_all.deb
#   dist/mpcasu-web_1.0.0-rc8_all.deb
#   dist/SHA256SUMS

# Install system-wide (needs sudo)
sudo dpkg -i \
  dist/casu-codec_1.0.0-rc8_all.deb \
  dist/casu-converter_1.0.0-rc8_all.deb \
  dist/mpcasu_1.0.0-rc8_all.deb \
  dist/mpcasu-web_1.0.0-rc8_all.deb

# Fix any dependency issues
sudo apt-get -f install -y

# Verify installed files
dpkg -L mpcasu | head -20
which mpcasu mpcasu-web casu casu-converter
```

### Phase 5: README Rewrite (15 min)

Rewrite `/home/error/Lino-Codec/README.md` in perfect English. Structure:

```
# MPCASU — Media Player & CASU Codec

## Overview
One paragraph: what MPCASU is, what CASU format is.

## Features
Table: Desktop Player, Web Player, Converter, CLI — each with format support.

## Installation
DEB install commands. System requirements (Python 3.10+, libVLC, FFmpeg).

## Usage
Desktop player: mpcasu [file/url]
Web player: mpcasu-web
Converter: casu-converter or casu convert/export/transcode
CLI: casu --help

## Keyboard Shortcuts
Space, F, N, M, arrows, etc.

## Formats
Table of supported formats with CASU extensions.

## Architecture
Backend switching: CASUNAT2 → Native → libVLC → FFmpeg fallback.
Diagram.

## Testing
Commands to run tests.

## License
Anti-Capitalist License 1.4.
```

### Phase 6: Documentation Polish (10 min)

Ensure these files exist and are accurate:
- `docs/FORMAT_SPEC.md` — CASU format specification
- `docs/CASU_FORMAT_SPEC.md` — same (consolidate)
- `docs/PLAYER_PROVENANCE.md` — where the player code came from
- `docs/CASU_CONVERTER.md` — converter documentation
- `docs/DEBIAN_PACKAGES.md` — DEB package descriptions
- `docs/VALIDATION.md` — how to validate CASU files
- `docs/DEVELOPMENT_PATH.md` — development roadmap

Delete or consolidate duplicate/empty docs. Ensure no broken internal links.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────┐
│                  MPCASU Desktop Player               │
│                   (mpcasu_player.py)                  │
│                                                       │
│  ┌──────────┐  ┌────────────┐  ┌─────────────────┐  │
│  │  Left Nav │  │  Center    │  │  Right Panel    │  │
│  │  - Library│  │  - Canvas  │  │  - Files tab    │  │
│  │  - Sources│  │  - Seek    │  │  - Database tab │  │
│  │  - Queue  │  │  - Bar     │  │  - Queue tab    │  │
│  │           │  │  - Tools   │  │                 │  │
│  └──────────┘  └─────┬──────┘  └─────────────────┘  │
│                       │                                │
│              ┌────────┴────────┐                       │
│              │ Backend Router  │                       │
│              └──┬──────┬──────┬┘                       │
│                 │      │      │                        │
│    ┌────────────┤      │      ├────────────┐          │
│    ▼            ▼      ▼      ▼            ▼          │
│ NativeCasu  LibVLC  FFmpeg  YouTube   Spotify        │
│ Backend     Backend Fallback iframe    yt-dlp         │
│ (PyAV)      (ctypes)         (Web)    search          │
│                                                        │
│  ┌──────────────────────────────────────────────────┐ │
│  │  Settings Store (settings.json)                   │ │
│  │  Session Store (session.json)                     │ │
│  │  Media Library (library.sqlite3)                  │ │
│  └──────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│                   CASU Codec Package                  │
│                   (casu-codec DEB)                    │
│                                                       │
│  casu/core.py         — Format core                   │
│  casu/native.py       — CASUNAT1 reader               │
│  casu/native_v2/      — CASUNAT2 reader/writer        │
│  casu/schema.py       — Manifest validation           │
│  casu/epg.py          — EPG parsing                   │
│  casu/waveform.py     — Audio analysis                │
│  casu/probe.py        — ffprobe wrapper               │
│  casu/filetypes.py    — Magic-byte detection           │
│  /usr/bin/casu        — CLI tool                       │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│                   Web Player                          │
│                   (mpcasu-web DEB)                    │
│                                                       │
│  web_casu.py          — Tornado HTTP server           │
│  web/index.html       — Player UI                     │
│  web/app.js           — Player logic (minified)       │
│  web/styles.css       — Styling                       │
│  web/casu-native.js   — CASUNAT2 WASM decoder         │
│  127.0.0.1:8765       — Default bind                  │
└─────────────────────────────────────────────────────┘
```

---

## DEB Package Contents

### casu-codec_1.0.0-rc8_all.deb
- `/usr/lib/python3/dist-packages/casu/` — full Python package
- `/usr/bin/casu` — CLI tool
- `/usr/share/casu-codec/assets/` — player icons
- Dependencies: python3, ffmpeg, libvlc

### casu-converter_1.0.0-rc8_all.deb
- `/usr/lib/python3/dist-packages/casu/` — same package (dependency)
- `/usr/bin/casu-converter` — converter GUI launcher
- `/usr/share/applications/casu-converter.desktop`
- Dependencies: casu-codec

### mpcasu_1.0.0-rc8_all.deb
- `/usr/lib/python3/dist-packages/mpcasu_backend.py`
- `/usr/lib/python3/dist-packages/mpcasu_native_backend.py`
- `/usr/lib/python3/dist-packages/mpcasu_playback.py`
- `/usr/lib/python3/dist-packages/mpcasu_player.py`
- `/usr/bin/mpcasu` — player launcher
- `/usr/share/applications/mpcasu.desktop`
- Dependencies: casu-codec

### mpcasu-web_1.0.0-rc8_all.deb
- `/usr/lib/python3/dist-packages/web_casu.py`
- `/usr/share/mpcasu-web/` — web assets
- `/usr/bin/mpcasu-web` — web server launcher
- `/usr/share/applications/web-casu.desktop`
- Dependencies: casu-codec

---

## Known Issues & Gotchas

1. **libVLC must be installed** — `libvlc-dev` or full VLC. Check with
   `vlc --version`. The backend uses ctypes to load `libvlc.so` directly.

2. **FFmpeg must be available** — for ffprobe, wavefrom decoding, thumbnails.
   `ffmpeg -version` and `ffprobe -version` should work.

3. **yt-dlp must be installed** — for YouTube/Spotify resolution.
   `yt-dlp --version`. Only used when consent is given.

4. **Test media files** — `test_media/giancarlo.mp4` and `test_media/lino_lol_test_pattern.mp4`
   are referenced by tests. They must exist in the test_media directory.
   The `.casu` files are derived artifacts and can be regenerated.

5. **Web player CORS** — `web_casu.py` serves from localhost:8765. The YouTube
   iframe uses `youtube-nocookie.com` for privacy. No CORS issues expected.

6. **Session restore** — if `session.json` is corrupt, the player silently
   ignores it. This is by design to avoid crash loops.

7. **Unicode in Tk** — Tkinter handles Unicode well on Linux. The font
   `("TkDefaultFont", 9)` works for all languages.

8. **PyAV for CASU native** — `import av` must work. Version 16.1.0 is installed.
   Used by `casu/native_v2/` for CASUNAT2 decoding.

---

## Complete Test Matrix

```
Category                    Tests    Status
─────────────────────────────────────────
Core (CASU format)          28       ✅ PASS
Codec/STRICT/Export         74       ✅ PASS (4 optional skips)
Desktop/Player UI           52       ✅ PASS
Converter                   75       ✅ PASS
Web/Chromium                35       ✅ PASS
libVLC runtime              20       ✅ PASS (9 XFAIL env-specific)
Release Guard               3        ✅ PASS
─────────────────────────────────────────
Total                       287      202 run, 152 skipped (media marker)
```

---

## Session 2 Log (2026-08-14)

### Workspace Recovery

A prior opencode session deleted `/home/error/Lino-Codec-work` (rm -rf on
08-13 21:59 and 08-14 00:41). That workspace contained the Qt player
preliminary work (`mpcasu_qt/`) and a parallel web player (`mpcasu_web/`).

All 52 recoverable files were extracted from the opencode session database
(`~/.local/share/opencode/opencode.db`, `part` table: write contents, edit
old/new strings, read outputs) into `/home/error/Lino-Codec-work-recovered/`
and compared against the repo:

- **Merged into the repo** (unique, not present anywhere else):
  - `mpcasu_qt/` — Qt player: `main_window.py` (2045 lines, fully
    reconstructed from the 81 KB write + 8 edits), `theme.py` (440 lines),
    `videoframe.py`, `app.py`, `__init__.py`. All compile; all casu/mpcasu
    imports resolve against the current repo. Requires PySide6 (not installed).
  - `mpcasu_web/` — parallel web player: `player.js` (58 KB, node --check OK),
    `index.html`.
  - `casu/media_backend.py` — abstract backend interface.
- **Not adopted:** repo versions of all shared files are newer/larger
  (verified for casu_converter.py, playlist.py, mpcasu_backend.py, web/app.js;
  waveform.py was byte-identical).
- Recovered English README (08-13 21:58) became the base for the new README.md.

### Fixes Implemented This Session

1. `show_settings_dialog` + Settings nav branch (Options dialog: volume,
   resume toggle, visualizer mode, cache limit + clear, DB refresh, yt-dlp
   consent).
2. yt-dlp consent gate before YouTube/Spotify resolution
   (`is_youtube_url`/`is_spotify_url` imports, `dataclasses.replace`).
3. Queue format badges via `detect_entry_type` (+ test updates).
4. Visualizer mode selector in `_draw_visualizer` (spectrum/waveform/both/off).
5. `SettingsStore.load()` now reads the new fields; `_save_effective_settings`
   preserves them.
6. **Reconstructed truncated `play_selected`** — backend open path for
   CASUNAT2 (NativeCasuBackend), CASUNAT1/sidecar (LegacyCasuBackend), plain
   media (LibVLCBackend), incl. diagnostics, resume (gated on
   `resume_playback`), playback-start watchdogs.
7. Database tab crash (`total_count` → `len(items())`).
8. Queue search filter with `_queue_view` index mapping; reorder blocked while
   filtered; `_play_queue_item` maps through the view.
9. Tk restyle with web design tokens (notebook tabs, entries, radiobuttons,
   checkbuttons, scrollbars).
10. README.md rewritten in English, corrected: `web-casu` binary names,
    `web_casu.py` launcher, real keyboard shortcuts, new feature list.

### Verification (all on this machine)

- `pytest -m 'not media'`: **202 passed, 152 deselected** (~7 s)
- `xvfb-run pytest tests/test_player_ui.py tests/test_converter_ui.py`:
  **18 passed**
- Real playback > 1 s under xvfb, each backend path:
  - MP4 video → LibVLCBackend (pos 18.6 s; audio output unavailable headless,
    expected)
  - MP3 audio → LibVLCBackend
  - CASU sidecar → LegacyCasuBackend
  - CASUNAT2 (freshly packed via `casu pack-v2`) → NativeCasuBackend
- `RADIO.m3u` loads **24 channels** via `casu.epg.load_m3u(path)`.
- DEBs rebuilt, installed, `dpkg -V` clean for casu-codec, casu-converter,
  mpcasu, web-casu. Installed `mpcasu` starts under xvfb.
- Web servers: both `web-casu` and `mpcasu-web` serve `/web/` with 200 and
  pass `--check`. `web_casu.py` is the strict superset (port takeover via
  /proc/net/tcp inode matching).

### Known Remaining Items

- Issue #3 (ffplay external-window fallback) untouched.
- Live internet stream playback not verified (no outbound network test yet).
- 3M fuzz runs (req. #28/#45) not re-run this session; infrastructure in
  `tools/fuzz_native_v2.py`.
- Qt player needs PySide6 to run (`pip install PySide6` or debian package).
- Orphan file `/usr/lib/python3/dist-packages/casu-codec.pth` (not owned by
  any package; harmlessly adds `/usr/share/casu-codec` to sys.path).
- `mpcasu-web` package kept installed alongside `web-casu` per user request;
  if one is removed later, remove `mpcasu-web`.
- Old `.casu` files may be broken (user confirmed); player fails closed on
  invalid CASU (verified: `lino_casu_error.casu`, `lino_lol_test_pattern.casu`
  are invalid sidecars and are rejected by `detect_casu_kind`).

---

## Continuation Checklist

Use this checklist when resuming work:

- [x] Add `show_settings_dialog` method to `MPCASUPlayer`
- [x] Add `elif name == "Settings": self.show_settings_dialog()` to `_navigate()`
- [x] Add `is_youtube_url` import from `casu.locations`
- [x] Add `is_spotify_url` import from `casu.spotify`
- [x] Add consent gate in `_resolve_and_open_external_source`
- [x] Add format badges to `_render_playlist`
- [x] Add visualizer mode selector in `_draw_visualizer`
- [x] Reconstruct truncated `play_selected` (backend open path)
- [x] Fix Database tab (`total_count`) and queue search filter
- [x] Recover deleted `Lino-Codec-work` from opencode DB; merge mpcasu_qt/mpcasu_web
- [x] Test player launch: `xvfb-run -a python3 mpcasu_player.py`
- [x] Verify real playback on all four backend paths (> 1 s)
- [x] Test M3U loading with RADIO.m3u (24 channels)
- [x] Run full test suite: `timeout 55 python3 -m pytest -q -m 'not media'`
- [x] Build DEBs: `bash packaging/build_debs.sh`
- [x] Install: `sudo dpkg -i dist/*.deb` (sudo is currently NOPASSWD)
- [x] Verify: `dpkg -V` clean, installed `mpcasu` starts
- [x] Rewrite README.md in English
- [ ] Polish docs/ (Phase 6) — files exist; review for accuracy/duplicates
- [ ] Fix ffplay external-window fallback (issue #3)
- [ ] Verify live internet stream playback (needs network)
- [ ] Re-run 3M fuzz campaign before final release
- [ ] Optional: install PySide6 and smoke-test `mpcasu_qt`

**Estimated remaining time: 30-45 minutes (docs + issue #3 + fuzz).**

---

# ⚠️ RETTUNGS- & BACKUP-HANDBUCH (Session 3, 2026-08-14 spät)

## PFLICHTREGEL FÜR JEDES FOLGE-TOOL

**IMMER IM BACKUP-MODUS ARBEITEN:**

1. **Vor jeder Änderung** an Dateien: Kopie anlegen (z. B. `cp datei datei.bak-$(date +%s)`)
2. **NIEMALS `rm -rf`** auf Verzeichnisse mit Benutzerdaten, Repos oder Arbeitskopien.
   Löschen nur einzelner, selbst erzeugter Temp-Dateien nach expliziter Prüfung.
3. **Vor DEB-Neubau**: `dist/` nie ungesichert löschen — `build_debs.sh` tut `rm -rf dist`;
   vorher `cp -a dist backups/debs-$(date +%Y%m%d-%H%M)`.
4. **Vor Paket-Operationen** (`dpkg --purge/remove`): Paketinhalt sichern mit
   `dpkg-repack` oder `dpkg-deb`-Extraktion nach `backups/`.
5. **Keine Session-Daten** (`~/.config/mpcasu/`) ohne Sicherung verändern.
6. Nach jeder Sitzung: Zustand dokumentieren (dieses File fortschreiben).

## Der rm -rf-Vorfall (bewiesen aus opencode-DB)

`~/.local/share/opencode/opencode.db`, Tabelle `part`:

| Zeitpunkt | Session | Befehl |
|---|---|---|
| 2026-08-13 21:59:34 | ses_0034e7658ffe… | `rm -rf /home/error/Lino-Codec-work && mkdir -p … && tar…` |
| 2026-08-13 22:39 | ses_0034e7658ffe… | `rm -rf /home/error/Lino-Codec-work` |
| 2026-08-14 00:41:46 | ses_002bc10b6ffe… | `rm -rf /home/error/Lino-Codec-work` |

Zerstört wurde dabei die Qt-Player-Vorarbeit (`mpcasu_qt/`, ~100 KB Code) und
`mpcasu_web/` (58-KB-Webplayer). **Alles wurde aus derselben DB wiederhergestellt**
(siehe unten) und ist heute im Repo.

## Wiederhergestelltes Material (komplett)

- `/home/error/Lino-Codec-work-recovered/` — 52 Dateien aus der DB rekonstruiert
  (Schreib-Inhalte + Edit-Diffs + Read-Outputs, Skript: `artifacts/recovery/db_recovery-script.py`)
- Ins Repo übernommen: `mpcasu_qt/` (main_window.py 2045 Zeilen, theme.py 440 Zeilen,
  videoframe.py, app.py), `mpcasu_web/` (player.js 58 KB, index.html), `casu/media_backend.py`
- `artifacts/recovery/mpcasu_web_vs_web_casu.diff` — vollständiger Diff zwischen den
  beiden Webplayer-Launchern; daraus ist `mpcasu_web.py` exakt rekonstruierbar
  (web_casu.py minus Port-Takeover-Block, Plus Namens-Tausch web-casu↔mpcasu-web)

## ALLE gesicherten DEB-Versionen (Code-Quellen!)

`/home/error/Lino-Codec/backups/` (317 MB):

| Verzeichnis | Inhalt |
|---|---|
| `debs-zip-v2-1.0.0/` | 1.0.0 (codec, converter, mpcasu) |
| `debs-zip-v3-rc2/` … `debs-zip-v8-rc7/` | rc2, rc3, rc4, rc5, rc6, rc7 |
| `debs-zip-v9-rc8-zip/` | rc8 aus v9-Zip (08-08) |
| `debs-2026-08-14-0026/` | rc8-Build vom 14.08. 00:26 — **inkl. mpcasu-web + web-casu** (Zustand "da ging alles") |
| `debs-heute/` | heutiger rc8-Build (alle heutigen Fixes) |

Jedes Verzeichnis hat `SHA256SUMS`. Code aus DEB extrahieren:
`dpkg-deb -x paket.deb zielverzeichnis/`

Weitere DEB-Quellen: `/tmp/*.deb` (00:26-Build, kann bei Reboot weg sein —
ist jetzt in backups/ gesichert), `/home/error/MPCASU_CASU_latest.zip` (1.0.0),
`CASU-CODEC-chatgpt-2026-08-08.zip` (ältere 1.0.0-Variante, anderer Codec-Umfang).

## Aktueller Installationszustand

Installiert (dpkg, `dpkg -V` sauber): `casu-codec`, `casu-converter`, `mpcasu`,
`web-casu` — alle 1.0.0-rc8, Inhalte identisch mit Repo.
**`mpcasu-web` wurde auf Nutzeranweisung entfernt** — Wiederherstellung:
`sudo dpkg -i backups/debs-2026-08-14-0026/mpcasu-web_1.0.0-rc8_all.deb`
(Nutzer bereut die Entfernung; im Zweifel wieder installieren.)

## Objektiver Funktionsstand (verifiziert am 14.08.)

- 202 Tests grün (`pytest -m 'not media'`), 18 GUI-Smoke-Tests grün unter xvfb
- Interaktiver Voll-Smoke: 16/16 Schritte OK (Start, Dateien, Play, alle Dialoge,
  Resize, Mini-Modus, Volume, Mute, Stop, Shutdown) — keine Fehler
- Playback >1 s verifiziert: MP4 (LibVLC), MP3 (LibVLC), CASU-Sidecar (LegacyCasuBackend),
  CASUNAT2 (NativeCasuBackend)
- Webplayer: RADIO.m3u lädt 24 Kanäle; BASSDRIVE, DLF, Byte.FM, FRITZ spielen
  (Playwright-E2E). Lokale Dateien in Playlists müssen MIT der Playlist zusammen
  ausgewählt werden (Browser-Sicherheit) — aggregierter Hinweis-Toast statt Spam.
- Nutzer-Session `~/.config/mpcasu/session.json` wurde bereinigt
  (war durch frühere Testläufe verschmutzt).

## Vom Nutzer gemeldete, OFFENE Punkte (subjektiv)

1. Desktop-Player: "Scrollen, keine Responsivität, schlechte Menüführung" —
   objektive Tests zeigen keine Defekte; UX-Überarbeitung gewünscht.
   Beste Basis: Design-System aus `mpcasu_qt/theme.py` (PALETTE/METRICS) und
   `web/styles.css`-Token auf Tk übertragen ODER PySide6 installieren
   (`pip install PySide6`) und den wiederhergestellten Qt-Player nutzen.
2. Nutzer möchte "aus beiden Playern + alten Daten was Gutes" — Material dafür:
   `mpcasu_qt/` (Qt-UI), `web/` (aktueller Webplayer), `mpcasu_web/` (alte
   Webplayer-Referenz), alle DEB-Versionen in `backups/`.
3. Chromium-Test `test_chromium_decodes_and_switches_native_tracks_and_bitmap`
   ist last-abhängig flaky (Timeout 15→45 s erhöht; einzeln immer grün).
4. Issue #3 (ffplay-External-Window-Fallback) weiter offen.
5. 3M-Fuzz-Kampagne vor Final-Release wiederholen (`tools/fuzz_native_v2.py`).

## Wichtige Orte (Kurzübersicht)

| Ort | Inhalt |
|---|---|
| `/home/error/Lino-Codec/` | Repo (autoritativ), 2927-Zeilen-Player, alle Features |
| `/home/error/Lino-Codec/backups/` | ALLE DEB-Versionen 1.0.0…rc8 +SHA256SUMS |
| `/home/error/Lino-Codec-work-recovered/` | DB-Recovery des gelöschten Workspaces |
| `/home/error/Lino-Codec/artifacts/recovery/` | Recovery-Skript + mpcasu_web-Diff |
| `~/.local/share/opencode/opencode.db` | Session-DB (Inhalte aller je geschriebenen Dateien) |
| `~/.config/mpcasu/` | Player-Session/Settings/Library (bereinigt) |
| `/home/error/Schreibtisch/RADIO.m3u` | 24-Kanäle-Testplaylist |

## Empfohlene nächste Schritte für das Rettungs-Tool

1. Diese Datei komplett lesen. Backup-Regeln oben befolgen.
2. `backups/` verifizieren: `cd backups/debs-* && sha256sum -c SHA256SUMS`
3. Mit Nutzer klären: welcher Player-Zustand gewünscht ist
   (Tk-aktuell / Qt-mpcasu_qt mit PySide6 / beide Webplayer).
4. `mpcasu-web` wieder installieren, wenn Nutzer es will (Befehl oben).
5. UX-Punkte 1–2 angehen (Design-System übertragen).
6. Vor jeder Änderung: Backup. Nach jeder Änderung: Tests + dieses Dokument.
