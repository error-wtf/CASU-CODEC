# Test report

## 2026-08-09 — current consolidated verification

- Fast behavior suite: **108 passed, 29 media tests deselected**.
- Generated STRICT + CASUNAT2 + native-player + installed-libVLC suites:
  plus bounded-probe/libass and authorized real-PGS tests: **54 passed**.
- Native-player behavior alone: **11 passed**, including no-tempfile playback,
  A/V/subtitle delivery, transactional seek, overlapping PCM-block trim and
  pause/stop/close flush behavior.
- Measured sink latency drives the native scheduling clock when available;
  unsupported non-1.0 native-audio rate changes fail closed instead of silently
  desynchronizing PCM.
- A stored legacy playback rate automatically falls back to a visible 1× when
  opening native audio instead of aborting media startup.
- Per-media audio/video/subtitle selections and bounded audio/subtitle delays
  survive SQLite reopen; both native scheduling and libVLC microsecond APIs are
  behavior-tested.
- A real reference video and a source-deleted CASUNAT2 album cover produce
  bounded PPM thumbnails; repeat lookup reuses the source-stat-versioned cache
  and the library preview remains asynchronous.
- A real MP3 attached-picture stream converts to a bounded, hashed PNG
  `cover-art` attachment, is not misclassified as video and is presented by the
  native audio player after source deletion.
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
- Installed libVLC entered active playback and advanced time, but its headless
  development runtime logged unavailable H.264 decode and no Pulse/ALSA output;
  this is recorded as an open runtime-matrix failure, not a pass.

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
