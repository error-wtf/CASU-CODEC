# MPCASU feature completion matrix — updated 2026-08-09

| Feature | Backend | UI | Evidence | Status |
|---|---|---|---|---|
| Installed-libVLC legacy playback | in-process shared library | embedded surface/controls | runtime API tests; full codec matrix open | PARTIAL |
| URL playback | libVLC locations | real URL dialog | capability test | PARTIAL |
| CASUNAT1/sidecar compatibility | verified extraction/source | labeled compatibility | unit/media tests | PASS |
| Native CASUNAT2 video | indexed key/tile reconstruction | Tk frame sink | digest + player tests | PASS reference path |
| Native CASUNAT2 audio | timestamped PCM + measured libpulse-simple latency | volume/mute | byte-exact/clock tests | PASS reference path |
| CASUNAT2 cover art/tags | bounded hashed PNG attachment + bounded manifest metadata | native audio canvas + library thumbnail + media info | real attached-picture source deletion and limit tests | PASS reference path |
| CASUNAT2 seek | generation cancel/cache invalidation + PCM trim | timeline/frame step | behavior test | PASS reference path |
| No CASUNAT2 tempfile | independent backend | n/a | tempfile forced to fail | PASS |
| Play/pause/resume/stop | both backends | controls/hotkeys | controller/backend tests | PASS reference path |
| Playback rate | libVLC; native video-only | rate control | fail-closed native-audio test | PARTIAL — native audio is 1.0x until a real resampler exists |
| Audio/video track selection | both backends | dynamic menus | runtime state tests | PARTIAL matrix |
| Subtitle/chapter selection | libVLC plus native text/libass/bitmap/chapter path | dynamic controls + clickable bounded timeline markers | runtime RGBA/text/chapter/seek behavior tests | PASS reference matrix |
| Native text/rich/bitmap subtitle/chapter | decoded packets, ASS/SSA libass RGBA, typed alpha-bounded PGS/DVD/DVB/XSub RGBA and chapter seek | transparent/text/bitmap overlay + dynamic chapter menu/timeline | generated and authorized 4-format source-deletion + RGBA/sink/GUI tests | PASS reference matrix; broader platform/malformed coverage open |
| Playlist reorder/save/load | player model | controls | runtime methods | PARTIAL product |
| Functional navigation | concrete actions only | sidebar/compact rail | pseudo entries removed | PASS |
| Source-resolution STRICT | production converter | mode selection | unit + generated media | PASS |
| PCM waveform/spectrum | absent | explicitly unavailable | truthful state | OPEN |
| Energy telemetry | absent | explicitly unavailable | truthful state | OPEN |
| SQLite library/settings/devices | transactional search/scan/resume/favorites/playlists + per-media tracks/delays | watched folders + library/sync menus + async thumbnails | behavior + real-media/GUI smoke | PASS reference core |

The exact legacy codec set is whatever the installed VLC build and its modules
actually expose. MPCASU does not reject a libVLC-readable file by extension,
but it will not claim an untested universal matrix before Gate E step 59.
