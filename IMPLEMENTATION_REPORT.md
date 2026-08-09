# Implementation report

## 2026-08-09

### Gate 2 — Source-resolution STRICT: PASS

The production `analyze(..., mode="strict")` and converter path now use the
source-resolution STRICT decoder and state builder. The reduced 160×90 Gray8
analyzer is retained only as `preview_activity_analysis` for non-STRICT hints.

Implemented and behavior-tested:

- immutable padding-free active native planes with explicit layout;
- RGB/alpha and YUV 4:2:0, 4:2:2, and 4:4:4 geometry;
- 8/10/12/16-bit unsigned samples with fail-closed range checks;
- relevant color metadata in canonical and tile identity;
- rational source PTS/time-base validity bounds and decoded duration;
- presentation-order VFR and B-frame decoding without an FPS filter;
- coordinate/geometry/layout/metadata/active-byte tile hashes;
- exact HOLD, one-sample UPDATE, and format-change KEY_STATE behavior;
- unsupported layouts and non-monotonic presentation PTS fail closed.

Evidence is recorded in `RELEASE_GATE_STATUS.json` and `TEST_REPORT.md`.
This PASS closes only the STRICT gate. It does not close CASUNAT2, native
playback, converter completion, product UI, or release gates.

### Gate 2 — Native CASUNAT2 payload: PASS

`casu pack-v2` and `casu convert --container native-v2` now run the same real
source-to-native pipeline. It stores complete canonical key states, hash-linked
plane-aware tile updates, source-time-base frame timelines and canonical s16le
PCM blocks. The seek index contains validated file byte offsets. Generated-media
acceptance tests remove the source, reconstruct every target video state and
compare the concatenated PCM digest. CASUNAT1 remains a labeled compatibility
envelope.

### Gate 4 — Native player path: PARTIAL

`NativeCasuBackend` is independent from `LibVLCBackend`. It reconstructs video
from CASUNAT2 byte-indexed states, schedules video and PCM from measured
PulseAudio sink latency when available with a monotonic video-only fallback,
invalidates pending output transactionally on seek, trims an overlapping PCM
block to the seek sample, flushes audio on pause/stop/close, presents RGB frames
in the MPCASU canvas and writes s16le through libpulse-simple. Instrumented
tests prove frame/audio/subtitle delivery and make any tempfile creation fail.
Playback lifecycle transitions are serialized. If an old worker remains inside
a blocking PCM write past the bounded join timeout, seek refuses the restart
and retains the stop signal; it never clears cancellation and starts a competing
generation. Rapid forward/backward seek tests prove that only the final video
frame generation and correctly trimmed PCM samples reach the sinks.
Live audio, video and subtitle selection now uses the same serialized restart
at the measured position. It flushes old PCM, invalidates queued canvas work,
clears the prior subtitle and reopens the PulseAudio stream for a new audio
sample-rate/channel geometry. A two-video/two-audio/two-subtitle fixture proves
that only the selected English stereo/2-kHz PCM, video and subtitle arrive.
Native device discovery now parses only bounded PipeWire `Audio/Sink` nodes via
the shared monitored subprocess runner and retains `default` when PipeWire is
absent. The selected node name is supplied to `pa_simple_new`; live selection
stops the old generation, flushes, drops the prior sample spec and restarts at
the measured position. Inventory filtering/offline fallback and an instrumented
USB-DAC live switch pass. Physical hotplug remains unclaimed.
Worker exceptions now perform the same fail-closed cleanup before publishing
`ERROR`: the media position is captured, generation cancelled, PCM flushed,
video/subtitles invalidated and audio clock reset. The bounded backend error is
shown by MPCASU. An instrumented one-shot sink underrun then replays successfully
from the same open CASUNAT2 container.
Native audio rates from 0.25× through 4× use bounded deterministic linear PCM
resampling with channel alignment and s16le clipping. Rate changes stop the old
worker, flush pending PCM, reset the audio clock and restart at the measured
media position. Sink latency and elapsed wall time are scaled into media time.
This changes pitch; pitch-preserving time-stretch, real-device long-duration
drift evidence and the device matrix remain open.
The audio master is re-anchored from every absolute block PTS and measured sink
latency rather than accumulated deltas. New observations are monotonic against
already reached media time, and invalid or implausible (>60 s) driver latency is
ignored. A deterministic 21,600-block simulation covers six media hours at 1.5×
with changing latency and zero cumulative drift; it does not replace hardware
measurement.

### Gate 3 — Integrity, recovery and hostile-input safety: PASS

The main reader is streaming and enforces file/manifest/chunk/count budgets.
Key/tile/audio decompression is constrained to exact metadata-derived output
lengths. Integrity/footer/order/offset checks and declared-prefix recovery fail
closed. A deterministic 10,000-mutation campaign completed with zero unexpected
accepts, crashes or hangs; exact evidence is in `FUZZ_REPORT.md`.

### Gate 5 — Media/converter product core: PARTIAL

CLI and GUI share `ConversionEngine`, profiles and jobs with real progress,
fail-closed cancellation, per-file failure isolation, CLI retry and an atomic
machine-readable journal/report. CLI and GUI can resume only outputs whose
size and SHA-256 still match the exact prior job/profile list. Independent
batches in one directory receive deterministic distinct journal identifiers.
The shared engine now emits monotonic batch-level progress with measured elapsed
time, throughput ETA and explicit state; results retain actual conversion time,
so CLI reports and GUI status no longer implement competing estimators.
The GUI now passes a validated retry count to the same engine and opens bounded
prior reports with per-file status, attempts, measured duration and errors.
Completion and cancellation reports now pass the same bounded validator and are
atomically replaced. A typed `ConversionCancelled` carries verified completed
results plus active-job/attempt evidence; the GUI records the remaining queue as
cancelled and never labels the interrupted batch complete. Engine and real Tk/
Xvfb tests prove the Cancel event reaches this path and the active target remains
absent.
Immutable backend-neutral track/chapter/device/event models and a transactional
SQLite library (scan, resume, favorites, playlists) is behavior-tested.
The player queue and sidebar now render from one bounded, duplicate-free
`PlaylistModel`; session/playlist persistence, selection, reordering and removal
no longer treat Tk widgets as independent data stores.
Attached PNG, JPEG and WebP cover pictures now convert to bounded hashed PNG
attachments, remain audio-only in stream selection, survive source deletion and
display in both the native audio canvas and library thumbnail path. Decode is
rejected before invoking FFmpeg when probed geometry is missing, non-positive,
exceeds 8192 pixels per axis or exceeds a 256 MiB decoded RGBA budget. ASS/SSA styling renders through
bounded libass RGBA with a text fallback. An authorized real PGS fixture converts
through FFmpeg's bitmap subtitle-video boundary to typed, hashed, alpha-bounded
RGBA regions, survives source deletion, and renders correctly after seeking into
an active cue. Authorized DVD, DVB and XSub fixtures now pass the same public
source-deletion path; a malformed DVB secondary audio PID is isolated and
reported without discarding valid streams. Broader platform and runtime
matrices remain open.
Bounded source-stat-versioned thumbnails, watched-folder
rescans, SQLite library search and per-media track/audio-delay/subtitle-delay
preferences are wired into the UI.
Backend-neutral chapter descriptors now also draw bounded, clickable timeline
markers; selecting one performs a real backend chapter seek and highlights the
active chapter.

## 2026-08-08 (previous state)

### Gate 2 — Source-resolution STRICT: PARTIAL (superseded by 2026-08-09 evidence)

Implemented `casu.strict` with:

- immutable multi-plane canonical frames;
- 8/16-bit plane validation;
- source PTS/time-base model;
- FFmpeg source adapter preserving presentation timestamps and native
  `yuv420p`, `yuv420p10le`, `yuv444p`, gray and RGB plane layouts;
- exact per-plane tile hashing;
- chroma/subsampled-plane and alpha-sensitive HOLD vs UPDATE decisions;
- monotonic PTS validation and state-map intervals.

Evidence: strict unit tests cover identical frames, one changed plane sample,
16-bit planes and PTS-derived timestamps.

Targeted media evidence now covers a real `yuv420p` fixture with native
full-resolution luma, subsampled chroma planes and source PTS. Still open for
PASS: production coverage for every required source format (including alpha,
12-bit, B-frame/VFR edge cases and complete color metadata), plus the full
conformance corpus. The existing 160×90 grayscale path remains an activity
hint and is not used as proof of STRICT identity.

No 1.0 release claim is made while this gate is PARTIAL.

### Gate 1 — Native CASUNAT2 payload: PARTIAL (superseded by 2026-08-09 PASS)

Implemented `casu.native_v2` as a standalone deterministic binary container
primitive with typed chunks, atomic writing, key-state/update byte offsets,
seek-index serialization, bounded reads and SHA-256 integrity verification.
It now also serializes lossless canonical video key-state planes and
subsampled-plane tile updates, with a reconstruction cache, timestamped audio
blocks, deterministic subtitle packets and chapter tables. The source file is
not required to read the written chunks.

Still open for PASS: recovery-point recovery validation across truncated files,
native player/audio sinks and end-to-end codec roundtrip fixtures against real
media.

Lossless timestamped CASUNAT2 audio blocks are now implemented with explicit
sample rate, channel layout, sample format, sample count and PTS metadata.

### Gate 6 — Integrity/recovery/resource limits: PARTIAL (superseded by 2026-08-09 PASS)

CASUNAT2 now writes periodic recovery-point chunks and the reader enforces
manifest, chunk-count, chunk-size and total-file limits while validating
truncation, chunk types, recovery offsets and SHA-256 integrity. A recovery API
now returns only the last writer-declared complete prefix after interruption;
tests cover truncation before END. Fuzzing and a complete corrupt-file corpus
remain open.
