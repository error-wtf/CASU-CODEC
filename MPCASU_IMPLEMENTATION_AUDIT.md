# MPCASU implementation audit — updated 2026-08-09

A visible control counts only when it invokes tested behavior.

## Playback architecture

| Area | Status | Evidence / boundary |
|---|---|---|
| Ordinary VLC-compatible media | PASS contract / PARTIAL runtime matrix | `LibVLCBackend` embeds the installed shared library without extension/scheme allow-list or subprocess. Generated fixtures prove six audio, one callback-delivered video, three external-subtitle and loopback HTTP playback/seek paths; nine compressed-video paths XFAIL in the privileged harness while non-root H.264 succeeds, so physical/broader-network/platform coverage stays open. |
| CASUNAT1/sidecar compatibility | PASS | Validated source or verified envelope extraction feeds libVLC and is labeled compatibility. |
| Native CASUNAT2 video | PASS for reference path | Independent `NativeCasuBackend` reconstructs indexed key states/tile updates and presents source-sized RGB frames to the MPCASU canvas. |
| Native CASUNAT2 audio | PASS for reference path | Timestamped s16le PCM is written directly through libpulse-simple; measured sink latency feeds the media clock and instrumented sinks prove exact delivered bytes. |
| Native seek | PASS for reference path | Seek changes generation, cancels pending work, invalidates video output, flushes audio, trims an overlapping PCM block to the target sample and resumes from indexed state. |
| Temp legacy extraction for CASUNAT2 | REMOVED | Acceptance monkeypatches tempfile creation to fail and playback still completes. |
| Native subtitle/chapter/device model | PARTIAL device matrix | Text packets, libass RGBA and typed alpha-bounded PGS/DVD/DVB/XSub RGBA render/clear/seek; chapter seek and default Pulse device model work. The device-switching/platform matrix remains. |
| Long-run audio-master drift correction | PARTIAL | PulseAudio `pa_simple_get_latency` feedback drives the reference clock and is behavior-tested; real-device long-duration drift/prebuffer evidence is not complete. |

## User-facing behavior

Real play/pause/resume/stop/seek, rate, volume/mute, model-backed playlist reorder/save/load,
URL opening, dynamic track/output/chapter menus and frame controls where supported,
fullscreen, session resume and media information are wired. Visible sidebar entries now
route to concrete file, URL, playlist, focus or selection actions. Removed
catalog/favorites/hub entries are not advertised as if implemented.

MPCASU deliberately reports unavailable telemetry and PCM visualization instead
of inventing waveforms or energy savings. The UI is still a Tk development UI;
SQLite library/resume/favorites/playlists, atomic playback settings and native
text-subtitle overlay, watched-folder rescans and bounded persistent search now
exist. Video and source-independent cover thumbnails decode into a bounded
source-stat-versioned cache without blocking the UI. ASS/SSA source styling is
rendered through bounded libass RGBA with text fallback. Real PGS subtitles use
typed, hashed, alpha-bounded RGBA regions and survive source deletion; the
broader malformed/platform subtitle matrix and responsive Qt target remain open.

## Acceptance evidence

- fast suite: 134 passed, 62 media tests deselected;
- exact-runtime generated libVLC matrix: 15 passed, 9 xfailed; real FLAC
  rate/delay/pause/resume passes, while nine video cases xfail because the
  installed runtime delivered no video callback frame;
- combined generated STRICT/native-v2/native-player/installed-libVLC suites:
  54 passed, plus a focused 4-format authorized PGS/DVD/DVB/XSub
  source-deletion matrix;
- native-player backend: video/PCM delivery, tracks, transactional seek,
  display dimensions and fail-on-tempfile tests all pass;
- native converter media tests reproduce video and audio after source deletion;
- source-string pseudo acceptance assertions have been replaced with runtime
  API/state assertions;
- stable 1.0 remains blocked by the PARTIAL/OPEN gates in
  [`RELEASE_GATE_STATUS.json`](RELEASE_GATE_STATUS.json).
