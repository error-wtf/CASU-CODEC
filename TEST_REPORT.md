# Test report

## 2026-08-09 — current consolidated verification

- Fast behavior suite: **138 passed, 64 media tests deselected**.
- Generated exact-runtime libVLC matrix: **17 passed, 9 xfailed**. Six audio
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
  three packages and MPCASU contains the native backend: **PASS**.
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
