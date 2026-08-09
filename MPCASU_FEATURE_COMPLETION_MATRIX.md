# MPCASU feature completion matrix — updated 2026-08-09

| Feature | Backend | UI | Evidence | Status |
|---|---|---|---|---|
| Installed-libVLC legacy playback | in-process shared library | embedded surface/controls | generated matrix: 6 audio + Rawvideo + 3 subtitle + FLAC transport-control pass, 9 compressed-video runtime XFAIL | PARTIAL |
| URL playback | libVLC locations without scheme allow-list; false empty EOF normalized; URL userinfo redacted | real URL dialog | loopback HTTP redirect + PCM playback/seek + 404 + HLS AAC-in-TS + Basic-auth header/PCM | PARTIAL HTTPS/interactive-401/mutable-live/hostile-network matrix |
| CASUNAT1/sidecar compatibility | verified extraction/source | labeled compatibility | unit/media tests | PASS |
| Native CASUNAT2 video | indexed key/tile reconstruction | Tk frame sink | digest + player tests | PASS reference path |
| Native CASUNAT2 audio | timestamped PCM + bounded measured libpulse-simple latency + monotonic absolute-PTS clock | volume/mute | byte-exact plus six-hour/21,600-block zero-accumulation simulation | PASS instrumented reference; hardware drift open |
| CASUNAT2 cover art/tags | PNG/JPEG/WebP normalize to bounded hashed PNG + bounded manifest metadata; pre-decode geometry/RGBA limits | native audio canvas + library thumbnail + media info | real three-format attached-picture source deletion and limit tests | PASS reference matrix |
| CASUNAT2 seek | serialized generation cancel, fail-closed worker join, cache invalidation + PCM trim | timeline/frame step | blocked-write and four-direction rapid-seek behavior tests | PASS reference path |
| No CASUNAT2 tempfile | independent backend | n/a | tempfile forced to fail | PASS |
| Play/pause/resume/stop/frame-step/error replay | both backends; native fail-closed sink/decode cleanup; libVLC next-frame `void` ABI | controls/hotkeys + concrete error | controller/backend, pixel-distinct Rawvideo RV32 step and transient-underrun replay tests | PASS reference path |
| Playback rate | libVLC plus native 0.25×–4× channel-aligned s16le resampling/audio-clock scaling | rate control | native PCM geometry/transactional live-rate plus real libVLC FLAC 1.5x/delay/pause/resume | PASS speed/pitch reference path; pitch-preserving time-stretch open |
| Audio/video track selection | both backends; native transactional restart and Pulse format reopen | dynamic menus + concrete-ID cycling | native 2-video/2-audio/2-subtitle isolation + real libVLC MP4 two-audio selection + noncontiguous-ID cycle regression | PASS reference; platform matrix partial |
| Audio output selection | bounded PipeWire Audio/Sink inventory + selected node passed to Pulse simple | dynamic reported-device menu | JSON filter/offline fallback + live USB-DAC switch | PASS instrumented native reference; physical hotplug/platform matrix open |
| Subtitle/chapter selection | libVLC plus native text/libass/bitmap/chapter path | dynamic controls + clickable bounded timeline markers | real libVLC external/embedded/two-chapter selection + native RGBA/text/chapter/seek tests | PASS reference matrix |
| Native text/rich/bitmap subtitle/chapter | decoded packets, ASS/SSA libass RGBA, typed alpha-bounded PGS/DVD/DVB/XSub RGBA and chapter seek | transparent/text/bitmap overlay + dynamic chapter menu/timeline | generated and authorized 4-format source-deletion + RGBA/sink/GUI tests | PASS reference matrix; broader platform/malformed coverage open |
| Playlist reorder/save/load | one bounded duplicate-free player model | synchronized library/queue controls | unit + real Tk add/move/remove behavior | PASS reference product |
| Functional navigation | concrete actions only | sidebar/compact rail | pseudo entries removed | PASS |
| Source-resolution STRICT | production converter | mode selection | unit + generated media | PASS |
| PCM waveform/spectrum | absent | explicitly unavailable | truthful state | OPEN |
| Energy telemetry | absent | explicitly unavailable | truthful state | OPEN |
| SQLite library/settings/devices | transactional search/scan/resume/favorites/playlists + per-media tracks/delays | watched folders + library/sync menus + async thumbnails | behavior + real-media/GUI smoke | PASS reference core |

The exact legacy codec set is whatever the installed VLC build and its modules
actually expose. MPCASU does not reject a libVLC-readable file by extension,
but it will not claim an untested universal matrix before Gate E step 59.
