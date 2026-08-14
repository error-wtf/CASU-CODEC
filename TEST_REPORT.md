# Test report

## 2026-08-13 — final split verification after converter/web hardening

- The native parser completed **3,000,000 deterministic mutation executions**
  across seeds 2026081301–2026081330: 2,994,529 rejected, 5,471 still-valid
  containers fully verified, **0 unexpected results, crashes or hangs**.
- Converter inspection is asynchronous and every production profile value is
  captured before its worker starts. Tile size/key-state interval are validated
  controls. Central FFprobe calls are limited to 30 seconds and 64 MiB JSON.
  The exact 20-file acceptance isolates 17 valid and 3 corrupt sources. Atomic
  JSON/CSV/Markdown evidence includes hashes, tool versions, native counters,
  verification and warnings.
- Remote HTTP(S) M3U/XMLTV import now works through the bounded same-origin web
  launcher proxy; file/pseudo URLs remain rejected. Source changes reset A–B.
- Final bounded groups: **202 passed** in the non-media core matrix;
  **74 passed, 4 opt-in skips** for native-v2/STRICT/export; **52 passed** for
  native/desktop; **75 passed** for converter/transcode; **35 passed** for web
  and Chromium; **20 passed, 9 environment XFAIL** for exact-runtime libVLC;
  release guard **3 passed**. All individual groups finished below 60 seconds.
- The monolithic `-m media` aggregate was deliberately terminated at the
  mandated 60-second ceiling while still progressing. No component hang was
  indicated; the complete 354-test collection is therefore verified through
  the bounded split commands above.
- GUI tests now use a temporary XDG profile and cannot restore or overwrite the
  user's real playlist/session. Package inspection confirms CASU installs no
  GStreamer/VLC/system codec plugin or media-environment override.

## 2026-08-13 — streams, EPG, recording and VLC-control parity

- Desktop and web now parse bounded Extended M3U and XMLTV data, show searchable
  current/next schedules and play selected live channels. Local and loopback
  fetch/parser plus real Chromium EPG coverage pass.
- Desktop adds atomic verified all-stream recording, disc/camera/screen/audio
  source entry, bounded asynchronous folder import, media bookmarks, A–B,
  go-to, snapshots, title navigation, aspect/crop/zoom/deinterlace, stereo
  modes and runtime-reported libVLC equalizer presets.
- The web player adds A–B repeat for browser-decoded media, PNG snapshots and
  playback speed while refusing unsupported embedded/native cases explicitly.
- Focused desktop/core/record/library block: **108 passed** in 14.87 s. Web,
  real Chromium, launcher and transcode block: **30 passed** in 13.33 s.
  Native path block: **37 passed, 4 skipped** in 6.11 s. Installed libVLC
  runtime block: **20 passed, 9 environment-specific XFAIL** in 26.07 s.
  The remaining converter/codec/file block passed **136 tests**; its only
  mixed-run failure was a local HTTP fixture timeout, which passed in isolation
  in 0.57 s. Every individual command remained below 60 seconds.
- A packaged H.264/AAC Xvfb smoke with no Pulse/ALSA server reproduced a real
  synchronous libVLC shutdown hang and continuous output retry. Backend
  ownership is now detached from Tk immediately and third-party stop/release
  runs on a daemon cleanup thread; the identical failure environment exits
  cleanly in **2.36 s**. The updated focused core/player/record block passes
  **104 tests** in 14.53 s with isolated settings.

## 2026-08-13 — automatic playback-route switching

- Desktop local-file routing is now content based: CASUNAT2 magic selects the
  independent native decoder, CASUNAT1 magic selects the verified compatibility
  backend, valid JSON sidecars resolve their hash-checked source, and ordinary
  media uses libVLC regardless of filename. A misleading `.casu` suffix falls
  back only after FFprobe proves a real audio/video stream; malformed CASU is
  still rejected.
- The browser recognizes CASUNAT1/2 magic even after a rename. Normal HTML5
  failures switch to local FFmpeg automatically; a native CASUNAT2 prepare/play
  failure now switches through the verified CASU exporter to adaptive MP4/WebM,
  retaining CASU source labeling in the UI.
- Generated renamed-CASUNAT2 server fallback reconstructs both video and audio.
  Route/export/web block: **128 passed**. Desktop GUI/native block: **35 passed**.
  Real Chromium web block: **13 passed**. Installed-libVLC runtime block:
  **29 passed**. Complete isolated-X/loopback system-interpreter suite:
  **319 passed, 6 opt-in corpus tests skipped in 56.27 s**. Every command
  remained below 60 seconds.

## 2026-08-13 — System-PyAV, replay stability and converter report completion

- Debian's `/usr/bin/python3` and packaged PyAV 16.1 decode the STRICT reference
  fixture with exactly the same PTS, time base, duration, pixel format, plane
  geometry and active-plane SHA-256 values as the monitored FFmpeg adapter.
  STRICT plus CASUNAT2 acceptance on that production interpreter: **33 passed,
  4 explicitly opt-in corpus fixtures skipped**.
- Native playback now tracks requested transport intent independently of a
  transient worker state. Rapid seeks, rate/device/track restarts and a replay
  after natural EOF cannot strand the backend paused; the rapid-seek and EOF
  replay cases passed **20 consecutive repetitions**, followed by the complete
  player-core block (**41 passed**).
- The bounded converter report now has live text/status filtering, a scalable
  table and atomic filtered CSV export. CSV text fields are protected against
  spreadsheet formula injection. Converter job and real Tk/Xvfb report tests:
  **12 passed** and **8 passed**.
- Network source labels now redact URL userinfo plus common query tokens and
  signatures and bound malformed display values. The actual stream URL is not
  modified. Hardware decoding is reported truthfully as disabled.
- Complete repository run using the packaged system interpreter: **315 passed,
  6 opt-in corpus tests skipped in 56.71 s**. `git diff --check`, Python
  compilation, shell/JavaScript syntax and desktop-file validation: **PASS**.
- All four RC8 Debian packages were checksum-verified, installed and passed
  `dpkg -V`. From a neutral `/tmp` directory, the installed CLI created and
  verified a 2-stream/48-chunk CASUNAT2 file and exported an MP4 containing
  video plus audio; both installed Tk applications constructed under Xvfb and
  the web launcher verified its assets. Installed libVLC playback as the
  non-root desktop user advanced to 0.591 s and ended cleanly.

## 2026-08-13 — Webplayer hardening and control completion

- The browser CASUNAT2 reader now checks bounded header/chunk fields, typed
  manifest/config topology, complete per-chunk hashes, exact seek-key coverage,
  PTS/descriptor agreement and explicitly keyed video format changes before or
  during decode. The real dynamic-format, 2-video/2-audio/2-subtitle,
  text/bitmap/chapter Chromium fixture passes.
- Normal local playback now associates selected SRT/WebVTT files, converts SRT
  timestamps to WebVTT, exposes a subtitle selector and passes a real cue test.
  YouTube embeds accept only exact YouTube host/ID forms and are controlled by
  the main play, seek, volume, mute and queue-end actions.
- Rapid source changes use a playback generation token; ended native playback
  replays from zero; audio buffers are cached; inactive-item deletion preserves
  the active queue index; object URLs and native resources are released.
- The loopback server rejects DNS-rebinding Host values and cross-origin API
  writes and sends CSP, frame-ancestor, permissions, referrer and MIME headers.
- Web group: **28 passed** in 12.35 s. Fast suite: **176 passed, 141 media tests
  deselected** in 4.44 s. Every command remained below 60 seconds.

## 2026-08-13 — CASUNAT2 codec hardening

- Central `CasuLimits`, strict JSON, unique typed streams, canonical matching
  `STREAM_CONFIG`, chunk/stream compatibility, PTS ordering, singleton
  structures, exact per-chunk hash coverage and complete seek-key coverage are
  implemented fail-closed.
- Full verification decodes and checks video keys/tiles/format changes, audio
  descriptors/timing, text/bitmap subtitle timing, chapters and attachment
  roles. Explicit format changes are immediately key-state bounded and random
  access tested.
- Recovery checkpoints bind their preceding prefix and own declaration; writer
  output size is bounded and file plus directory are fsynced before replacement.
- Adversarial format tests: **15 passed**. Codec/Core/Fuzz: **103 passed**.
  STRICT/native/validation/export/transcode: **95 passed, 4 optional skips**.
  Native player/thumbnail/waveform: **27 passed**. Real Tk/Xvfb: **12 passed**.
  Fast suite: **175 passed, 140 media tests deselected**.
- Deterministic 10,000-mutation campaign, seed 20260813: **9,986 rejected, 14
  fully verified, 0 unexpected** in 3.0 s.

## 2026-08-13 — full media converter

- New shared `media-to-media` conversion path for CLI and Tk GUI: **PASS**.
  It supports single/multiple/recursive inputs, deterministic targets, atomic
  output, progress, cancellation cleanup, retry, hash-verified resume and JSON
  reports.
- Generated output matrix: **38 passed** in 9.69 s. It covers all 14 advertised
  audio and all 18 advertised video extensions; remux/lossless, multiple
  A/V/subtitle tracks, metadata, chapters, cancellation and recursive CLI batch
  are included. The matrix found and fixed legacy FLV, MP2 and ALAC muxing/rate
  edge cases before packaging.
- Full converter/core regression block: **147 passed** in 23.67 s. Real Tk/Xvfb
  converter/player UI block: **12 passed** in 1.26 s. Current fast suite:
  **160 passed, 140 media tests deselected** in 3.81 s.

## 2026-08-13 — web compatibility playback fallback

- The actual Web Player UI automatically detects and plays a generated
  rawvideo/PCM NUT file that Chromium rejects natively through its loopback
  FFmpeg fallback in real Chromium/Playwright: **PASS** with a decoded 64×48
  video and nonzero duration.
- Adaptive target selection produces VP9/Opus WebM for Chromium/Firefox-like
  support and H.264/AAC MP4 otherwise. Generated legacy fallback matrix:
  **16 passed** in 3.28 s — MP3, FLAC, WMA, AIFF, Vorbis, Opus, AAC plus H.264,
  MPEG-4, MJPEG, HEVC, VP8, VP9, AV1, MPEG-2 and FFV1 across their representative
  containers.
- File upload/transcode/download, HTTP byte-range seeking, prohibited local and
  pseudo-URL rejection, and finite network-source streaming: **PASS**.
- Complete web group after the final credential and UI-automatic regressions:
  **26 passed** in 8.73 s. Current fast suite: **160 passed, 101 media tests
  deselected** in 3.85 s. Player hang/runtime block remains **46 passed, 9
  environment-specific expected XFAIL** in 27.79 s.
- The freshly installed `/usr/bin/mpcasu-web` was then exercised independently
  from `/tmp`: its real UI automatically converted and played the same rejected
  input as 64×48 video with 0.408 s duration, requested the output with HTTP
  `206`, and shut down cleanly: **PASS**.

## 2026-08-13 — rebuilt and installed Debian packages

- The repository README was reduced from an architecture/test transcript to a
  structured German install, quick-start, web, test and limitations guide.
- Fresh reproducible `1.0.0-rc8` Debian builds: **PASS** for `casu-codec`,
  `casu-converter`, `mpcasu` and `mpcasu-web`; all four entries in
  `SHA256SUMS`: **OK**. Generated Python bytecode is excluded, and
  `dpkg --verify` is clean for every installed package.
- Package-content inspection confirms the current exporter, URL resolver,
  measured waveform module, desktop applications/icons and complete web player.
- System installation via `dpkg -i`: **PASS** for all four packages; package
  database status is `installed` and `dpkg --verify` reports no changed files.
- Installed CLI smoke: `casu --version` and help: **PASS**.
- Installed real roundtrip: generated FFV1+PCM → CASUNAT2 → verified → MP4:
  **PASS**, with both video and audio confirmed by `ffprobe`.
- Installed MPCASU and converter construction under isolated Xvfb: **PASS**;
  the mini-player hides/restores its panels and geometry without a Tk callback
  exception. The smoke exposed and verified a restore-order race fix before the
  final packages were rebuilt and reinstalled.
- Installed desktop files, web JavaScript syntax and README byte identity:
  **PASS**.
- Final hang-focused block (native backend + player UI + installed libVLC):
  **46 passed, 9 environment-specific expected XFAIL** in 29.23 s. The
  installed GUI also opened, played and shut down the generated A/V sample
  under Xvfb in 3.8 s while reporting measured CPU/RAM instead of freezing.
- Final converter/core block: **105 passed** in 12.49 s. Final
  web/export/player-UI regression block: **20 passed** in 6.20 s.

## 2026-08-13 — bidirectional/web completion slice

- Current collection: **240 tests**. Fast suite: **158 passed, 82 media tests
  deselected** in 4.03 s. The non-libVLC media block contains **49 passed / 4
  optional corpus skips**; the installed libVLC block is reported separately.
- Current real-media groups: STRICT **10 passed**; CASUNAT2 **11 passed / 4
  optional corpus skips**; core **6 passed**; export **11 passed**;
  converter/player Xvfb **11 passed**; thumbnail/waveform **3 passed**.
- Installed libVLC privileged harness: **20 passed, 9 expected XFAIL**; the
  exact ten-format video matrix as non-root desktop user is **10 passed**.
- Reproducible Chromium multi-track/bitmap smoke: **3 consecutive passes** in
  1.50–1.61 s after explicitly closing its Web Audio context and isolating the
  browser profile. It switches
  among 2 video, 2 audio and 2 subtitle streams and reports one verified RGBA
  bitmap cue, one chapter, audio and video.
- Real bidirectional batch smoke: generated FFV1/PCM + MP3 → two standalone
  CASUNAT2 files → batch MKV export; `ffprobe` confirms audio and video+audio.
- Recursive CLI input layout and equal-name collision regressions: **8 passed**.

- Fast behavior suite: **149 passed, 79 media tests deselected** in 3.36 s.
- Reverse export: **11 passed**, including sidecar→FLAC, CASUNAT1→MP3,
  compatibility multi-A/V/text/chapter mapping, and source-deleted CASUNAT2
  A/V→MP4, multi-audio, text/styled-ASS subtitle, two-chapter reconstruction
  and timed default-bitmap subtitle burn-in.
- URL resolver and web surface: **6 passed** plus Node syntax check; direct
  streams remain untouched and YouTube resolution fails closed without a
  single combined HTTP result.
- Measured audio waveform: generated WAV and source-independent CASUNAT2 PCM
  both produce bounded nonzero peaks; invalid point budgets fail closed.
- Real Chromium CASUNAT2 browser smoke: **PASS**, including integrity-prefix
  SHA-256, deflate decoding, two source-resolution reconstructed frames, PCM,
  one timed text subtitle, one chapter and a 0.400-second A/V timeline after source conversion. It still
  passes with validated audio/timeline limits and the 512 MiB decoded-media
  memory ceiling.
- STRICT acceptance: **21 passed** in 1.92 s.
- Native-v2 acceptance: **11 passed, 4 opt-in corpus cases skipped** in 4.16 s.
- Native player backend: **22 passed** in 2.27 s.
- libVLC audio/transport: **8 passed**; loopback network/HLS/auth/tracks:
  **10 passed**; video/frame-step: **2 passed, 9 expected headless XFAILs**.
- The frame-step test now waits for libVLC's pre-pause callback queue to become
  stable; three consecutive bounded runs each produced one pixel-distinct step.
- The former normal-suite stall was test-fixture misuse: resolver tests no
  longer run STRICT analysis over a 17-minute file, while actual analysis uses
  a one-second FFmpeg-derived source. `tests/test_core.py`: **81 passed** in
  11.46 s.
- Real Tk/Xvfb player/converter tests: **10 passed**, including mini-player
  hide/restore/geometry behavior; the full native layout was
  also rendered at 1280×1024 without the former double-navigation clipping.
- Clean temporary Debian package build: **PASS** for codec/converter/player;
  content and `yt-dlp` dependency inspection: **PASS**.
- Clean wheel build/install and bundled web-file inspection: **PASS**.
- `compileall`, JavaScript syntax check and `git diff --check`: **PASS**.

## 2026-08-09 — current consolidated verification

- Fast behavior suite: **139 passed, 67 media tests deselected**.
- Generated exact-runtime libVLC matrix: **20 passed, 9 xfailed**. Six audio
  combinations expose real tracks and advance playback; SRT, WebVTT and ASS
  load as external tracks; Rawvideo/AVI writes real RV32 callback frames. Nine
  compressed-video combinations deliver no callback frame in the privileged
  harness and remain failed runtime coverage rather than advertised support.
  The same H.264 callback probe delivers one frame as the non-root desktop user;
  runner identity therefore remains an explicit matrix dimension.
- Real libVLC subtitle descriptions traverse the ABI's linked list past the
  synthetic `-1` Disable node; SRT/WebVTT/ASS menus expose concrete tracks.
- Legacy URLs are passed to installed libVLC access modules without a smaller
  MPCASU scheme list; empty/NUL sources fail safely and Windows drive paths are
  kept on the local-path API.
- A generated WAV behind a loopback HTTP redirect opens through libVLC,
  exposes PCM, advances playback and seeks to one second. A 404 becomes
  `ERROR`, not VLC 3's misleading zero-track/zero-time EOF.
- A generated six-second HLS VOD playlist serves AAC-in-TS segments over
  loopback HTTP; installed libVLC creates the audio track, advances its clock
  and seeks to three seconds.
- A Basic-auth HTTP fixture observes libVLC's expected Authorization header and
  real PCM playback. A separate behavior test proves URL userinfo never reaches
  display/controller/error strings.
- A growing HLS fixture initially publishes two AAC/TS segments, then the full
  playlist. libVLC reloads the manifest, requests the final new segment and
  plays beyond three seconds.
- An HLS discontinuity crosses independently muxed 44.1/48-kHz AAC-in-TS
  segments in order and reaches clean `ENDED`. VLC 3's public time rebases at
  the boundary, which is recorded rather than reported as continuous.
- A real MP4 with two AAC and two embedded `mov_text` tracks exposes linked-list
  descriptions and accepts selection of both audio and both subtitle IDs.
- A real AAC/MP4 fixture exposes two chapters and jumps to chapter 2 after
  correcting libVLC's `void` chapter/title setter ABI declarations.
- A real four-second FLAC fixture proves 1.5x rate, 125-millisecond audio
  delay, pause clock stability and resumed clock progress. The dummy sink's
  zero volume getter is recorded rather than misrepresented as physical output.
- A generated Rawvideo/AVI fixture proves one-frame navigation with exactly
  one new pixel-distinct RV32 callback while paused; the former erroneous
  integer return binding was corrected to libVLC's documented `void` ABI.
- Empty EOF classification waits through an explicit monotonic asynchronous
  startup grace period before declaring an opening failure.
- Three release-guard AST regressions distinguish prohibited direct
  string-in-source assertions from legitimate observed runtime status text.
- Generated STRICT + CASUNAT2 + native-player + installed-libVLC suites,
  including bounded-probe/libass, authorized real-PGS and the added JPEG/WebP
  cover variants: **56 passed**.
- Native-v2 media acceptance alone: **11 passed, 4 authorized-corpus cases
  skipped** when their opt-in fixture variables are absent.
- Focused authorized bitmap matrix: **4 passed** for real PGS, DVD, DVB and
  XSub inputs after deleting each source; DVB also proves malformed secondary
  audio-stream isolation.
- Native-player behavior alone: **11 passed**, including no-tempfile playback,
  A/V/subtitle delivery, transactional seek, overlapping PCM-block trim and
  pause/stop/close flush behavior.
- Current native-player backend suite: **22 passed**; a blocked old PCM write
  cannot cross a seek/restart boundary, and four rapid forward/backward seeks
  deliver only the final generation. Bounded chapter-marker
  positioning and a real clickable Tk/Xvfb timeline behavior test also pass.
- A live six-stream fixture switches between two video, two audio and two
  subtitle streams while playing. Only the final video, English subtitle and
  2-kHz stereo PCM reach the sinks; Pulse format reset is observed exactly once.
- Player track-cycle behavior selects backend-reported noncontiguous audio,
  video and subtitle IDs and excludes synthetic `-1`/duplicate entries instead
  of inventing zero-based libVLC track numbers.
- Bounded PipeWire inventory accepts only `Audio/Sink` nodes, deduplicates names
  and falls back to `default` while offline. A live USB-DAC switch flushes and
  resets Pulse format before exactly one selected-sink audio block is delivered.
- A one-shot instrumented audio underrun enters `ERROR` only after PCM flush,
  generation/canvas invalidation, subtitle clear and clock reset. MPCASU exposes
  the concrete bounded cause; replay succeeds on the same open container.
- Playlist model unit tests and a real Tk/Xvfb integration test prove that both
  visible lists stay synchronized across duplicate add, move and remove.
- Job-engine ETA tests prove monotonic overall progress, measured elapsed time,
  retry-regression clamping and zero ETA at completion; converter Tk construction passes.
- Three real converter Tk/Xvfb tests prove that the GUI retry value reaches the
  shared engine/report, a bounded prior report opens as a detail view, and the
  Cancel action reaches the engine and atomically publishes `CANCELLED` without
  leaving the cancelled job's target output.
- Measured sink latency drives the native scheduling clock when available.
  Native 0.25×–4× playback resamples channel-aligned s16le PCM, scales latency/
  elapsed time into media time and transactionally restarts a live worker.
- A 21,600-block simulation covers six media hours at 1.5× with changing sink
  latency and zero cumulative drift. Clock observations never regress, and
  non-finite, negative or over-60-second latency reports are ignored.
- A stored playback rate is applied to native audio and displayed truthfully;
  speed/pitch resampling is not described as pitch-preserving time-stretch.
- Per-media audio/video/subtitle selections and bounded audio/subtitle delays
  survive SQLite reopen; both native scheduling and libVLC microsecond APIs are
  behavior-tested.
- A real reference video and a source-deleted CASUNAT2 album cover produce
  bounded PPM thumbnails; repeat lookup reuses the source-stat-versioned cache
  and the library preview remains asynchronous.
- Real MP3 attached-picture streams carrying PNG, JPEG and WebP convert to a
  bounded, hashed PNG `cover-art` attachment, are not misclassified as video
  and remain available after source deletion. Missing, invalid or oversized
  cover geometry is rejected before decode (8192 pixels per axis and 256 MiB
  decoded RGBA budget).
- Audio manifests ignore `attached_pic` cover streams when selecting a timed
  primary video stream; covers remain preserved by the attachment pipeline.
- Container/stream tag canonicalization is count-, value- and total-size-bounded;
  the real attached-picture fixture retains title/artist and dispositions.
- FFprobe JSON is spooled under monitored output/time limits; excessive output
  and timeout processes are killed in behavior tests, while decoded STRICT
  frames enforce explicit dimension and byte ceilings.
- A generated ASS stream retains its complete styles/dialogue attachment after
  source deletion, renders through libass into a transparent bounded RGBA/PNG
  layer at media time and retains a playable plain-text failure fallback.
- Embedded font attachments are labeled `subtitle-font`; libass registration is
  protected by per-font, aggregate-data and filename limits.
- The authorized VideoLAN PGS fixture converts to a timed 904×144 alpha-bounded
  RGBA region on its 1920×1080 canvas, survives source deletion and renders
  after seeking into the active interval. Corrupt bitmap payloads fail closed.
- Shared converter-job tests cover atomic journal state, batch failure
  isolation, fail-closed cancellation, retry validation and resume only after
  output size/SHA-256 plus exact job/profile matching.
- Mid-batch cancellation preserves verified completed-result evidence, records
  the active job/attempt, leaves its target absent and exposes the remaining
  files as cancelled in the atomic GUI report.
- Independent batches in one output folder receive deterministic distinct
  journal names; a real native-v2 CLI rerun reported `resumed: true` without
  decoding the source again.
- Persistent library search escapes SQL wildcards, is result-bounded and skips
  its own database; watched folders survive repeated settings saves. The real
  library dialog construction smoke passes under Xvfb.
- Both backends expose shared chapter descriptors and the dynamic chapter menu
  construction smoke passes.
- Deterministic CASUNAT2 corruption campaign: **10,000 cases, 0 unexpected**.
- Converter GUI construction under an isolated X display: **PASS**.
- The libVLC decoder matrix uses bounded dummy sinks only to isolate decoder
  behavior from absent Pulse/ALSA/display hardware. Real-device playback stays
  open and is not inferred from the passing headless decoder cases.

The sections below retain earlier gate checkpoints for provenance.

## 2026-08-13 — File-function regression gate

- Complete isolated-X repository suite with a hard 60-second timeout:
  **328 passed, 6 external-corpus skips in 57.05 seconds**.
- Focused playlist/routing/upload/static-web block: **18 passed**.
- Desktop player/converter/backend block: **64 passed**; focused active-file
  removal rerun: **13 passed**.
- Real headless-Chromium web block: **30 passed**, including automatic legacy
  fallback, subtitles, renamed CASU and bounded playlist rejection.
- Atomic and bounded reads/writes now cover player playlists/session/settings,
  converter reports/journals, CASU sidecars and recovery reads. Interrupted web
  uploads and failed transcodes are cleanup-tested; recursive CLI discovery is
  bounded while walking and never materializes an unlimited pre-sort.

## 2026-08-09 — Phase 1 STRICT gate

- Compile: **PASS** (`python -m compileall`).
- Fast behavior suite: **64 passed, 15 deselected**.
- STRICT generated-media suite: **9 passed, 11 deselected**.
- Media coverage: real VFR PTS, presentation-ordered B-frames, YUV420P,
  YUV422P, YUV444P, YUV420P10/12/16, and YUVA420P.
- Mutation/negative coverage: RGB sample, chroma sample, alpha sample,
  10/12/16-bit sample, color metadata, resolution, unsupported format/layout,
  sample range, and non-monotonic PTS.
- Clean wheel build and isolated installed-wheel STRICT smoke: **PASS**.
- Clean temporary-tree Debian package build/inspection and extracted-package
  STRICT smoke: **PASS**.
- `git diff --check`: **PASS**.
- `python tools/release_gate_guard.py --gate strict`: **PASS**.

The unrestricted guard intentionally remains non-zero while later gates are
PARTIAL/OPEN.

## 2026-08-09 — CASUNAT2 and native-player evidence

- Fast behavior suite: **74 passed, 21 deselected**.
- Generated-media STRICT + CASUNAT2 plus installed-libVLC runtime suites: **16 passed**
  after attachment source-deletion coverage.
- Native converter: key state, tile update, PCM, real byte offsets, repeated
  key-state seek, and source-deletion video/PCM round trips: **PASS**.
- Native player: decoded video and PCM delivery, instrumented A/V timing, seek
  invalidation, tracks/devices, display conversion, and fail-on-tempfile: **5 passed**.
- CLI `pack-v2`, `verify`, and `info` against generated FFV1+PCM media: **PASS**.
- Compile and `git diff --check`: **PASS**.
- Deterministic native corruption campaign, 10,000 cases: **0 unexpected**.
- Clean wheel includes native backend/library/media/converter modules: **PASS**.
- Clean Debian codec/player builds, content/dependency inspection and extracted
  package import smoke: **PASS**.
- Repository `dist/` RC8 Debian artifacts rebuilt; `SHA256SUMS` verifies all
  four packages and MPCASU contains the native backend: **PASS**.
- MPCASU and converter real Tk construction under isolated X display: **PASS**.
- Global guard now reports only gates that are honestly still PARTIAL/OPEN;
  placeholder navigation and source-string pseudo-tests are gone.

## 2026-08-08 (previous state)

- Fast/unit suite: **49 passed, 6 deselected** (`pytest -q -m 'not media'`).
- Targeted source-resolution media test: **1 passed**; verified native
  `yuv420p` planes and source PTS from the fixture.
- The full long-running media/UI matrix is not claimed as passing yet. It
  requires the remaining playback, CASUNAT2 reconstruction and device tests.

## Release truth

Green unit tests do not close any release gate by themselves. Gate status is
tracked in `IMPLEMENTATION_REPORT.md`.
