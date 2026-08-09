# MPCASU player deep audit — updated 2026-08-09

This file records implemented behavior, not widget presence.

| Area | Status | Evidence / open boundary |
|---|---|---|
| Legacy media | PARTIAL release matrix | In-process libVLC 3.0.23 initializes, accepts paths independent of extension and exposes runtime version/plugins; broad codec/platform matrix remains. |
| Native CASUNAT2 video | PASS reference path | Lazy on-disk chunks, indexed key/tile reconstruction, source-sized CPU RGB conversion and Tk presentation. |
| Native CASUNAT2 audio | PASS reference path | Exact timestamped s16le blocks feed an instrumented sink and direct libpulse-simple output. Hardware latency/master-clock drift remains open. |
| Native playback rate | PASS speed/pitch reference path | 0.25×–4× deterministic channel-aligned PCM resampling, bounded clipping, rate-scaled audio clock and transactional live restart pass; pitch-preserving time-stretch remains open. |
| Native seek | PASS reference path | Serializes lifecycle transitions, refuses restart while an old PCM write remains blocked, then flushes/invalidate/reconstructs; four rapid directional seeks deliver only the final generation. |
| Native subtitles/chapters | PASS reference matrix | UTF-8 packets, ASS/SSA libass RGBA with bounded embedded fonts, and typed alpha-bounded PGS/DVD/DVB/XSub RGBA render/clear/seek; delays and chapter seek work. |
| CASUNAT2 tempfile | REMOVED | Test forces tempfile creation to fail while native A/V playback completes. |
| Track/output selection | PASS native reference / PARTIAL platform matrix | Live native A/V/subtitle switches transactionally restart at the measured position, discard old output and reopen Pulse for changed PCM geometry; dynamic menus use reported descriptors. Broad VLC/device/platform matrix remains. |
| Events/clock | PARTIAL | Lifecycle events and monotonic native scheduler work; position poll remains for timeline and audio hardware clock/drift evidence is open. |
| Native error recovery | PASS instrumented reference | A one-shot PCM sink underrun captures position/error, cancels generation, flushes/invalidate/clears, then replays successfully without reopening/extraction. Real hardware underrun corpus remains. |
| Navigation | PASS current actions | Every visible entry performs a file/URL/playlist/focus action; catalog/hub/fake pages were removed. |
| Library/resume/settings | PASS reference core | Transactional SQLite scan/search/favorites/resume/playlists, watched-folder UI, per-media track/delay preferences, bounded cached thumbnails and atomic settings exist. |
| GUI construction | PASS | MPCASU and Converter instantiate/update/destroy under isolated X display. |
| Energy/visualizer claims | HONESTLY ABSENT | Fake waveform/energy claims are not drawn; the unnecessary 50 ms visual timer was removed. |

## Remaining P0/P1 work

1. Make native audio device time the measured A/V master and run long drift,
   pause/resume and underrun tests on real hardware; instrumented blocked-write
   and rapid-seek generation tests now pass.
2. Expand bitmap fixtures across platforms and malformed inputs and complete
   the hotplug device matrix; the shared PGS/DVD/DVB/XSub renderer, clickable
   chapter timeline, text-delay controls and chapter names work.
3. Add exact-runtime VLC parity fixtures for common containers/codecs/subtitles/
   network protocols on Linux, Windows and macOS.
4. Migrate views incrementally to Qt without replacing the tested shared
   playlist model or playback backends.
5. Expand artwork beyond the passing PNG/JPEG/WebP attached-picture matrix to
   animated, HEIF and broader platform cases; current covers survive source
   deletion, are decode-budgeted and render in the native audio canvas/library.

Current evidence: 123 fast behavior tests, 56 targeted generated/probe/libVLC/PGS/cover cases,
native A/V/subtitle/no-tempfile sinks, both Tk construction smokes, clean wheel
and Debian package inspection. Stable 1.0 remains blocked by the live gate file.
