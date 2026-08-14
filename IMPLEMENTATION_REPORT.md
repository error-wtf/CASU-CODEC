# Implementation report

## 2026-08-13

### Converter evidence, bounded inspection and remote web guides

The graphical converter now exposes validated CASUNAT2 tile size and periodic
key-state interval controls. It captures every Tk profile value and target on
the UI thread, then performs probing and conversion in workers whose results
return through a lifecycle-safe queue. Quitting cancels its periodic callback;
a blocking probe cannot freeze the window. All shared FFprobe inspection is
bounded to 30 seconds and 64 MiB of JSON.

Conversion results now preserve source/output/profile SHA-256, tool versions,
frame, key-state, tile-update, HOLD, audio-block and subtitle-packet counts,
elapsed time, verification and warnings. The evidence is atomically exportable
as JSON, spreadsheet-safe CSV or Markdown. An exact 20-file/3-corrupt batch
proves per-file isolation. The parser gate additionally completed three million
deterministic hostile mutations with no crash, hang or unexpected acceptance.

The web player can load remote HTTP(S) Extended-M3U and XMLTV through the local
same-origin server, retaining request/response limits and rejecting local or
pseudo protocols. Playback-source changes now clear an old A–B loop. The final
repository verification is intentionally split into sub-60-second groups; a
single media aggregate was stopped at exactly 60 seconds while still making
normal progress.

### Automatic playback-route switching

Desktop playback no longer equates the `.casu` suffix with the CASU format.
Bounded content classification selects native CASUNAT2, verified CASUNAT1,
validated sidecar resolution or universal libVLC media playback. Consequently,
renamed native containers and sidecars work, extensionless media works, and a
misnamed `.casu` media file is accepted only after a real audio/video probe.

The web player applies the same magic-first classification. Browser-native
CASUNAT2 remains the preferred path, but decoder preparation/play failures now
upload the original verified container to the loopback server, reconstruct it
through the CASU exporter and continue automatically as browser-compatible
MP4/WebM. The existing HTML5-format fallback uses the same transition and the
UI continues to identify the original CASU source. The resulting complete
system-interpreter suite passes 319 tests under isolated X/loopback execution.

### Production interpreter, replay and report hardening

All Debian launchers use `/usr/bin/python3`, and the codec package depends on
distribution PyAV. The real PyAV/libav STRICT adapter is parity-tested against
the monitored FFmpeg adapter for decoded timing, format, plane geometry and
content. This prevents a user's Conda/default-shell interpreter from silently
changing the installed application's decoder environment.

Native playback now keeps explicit playback intent across rapid seek, rate,
track and output-device worker restarts. Natural EOF can be replayed from zero;
explicit pause, stop, close and error still clear the intent. This fixes the
short-file race that could leave playback paused after a seek or restart.

Large conversion batches can be inspected through live path/error text and
status filters in a scrollable table. The visible subset can be exported
atomically to CSV, with formula-like text escaped for safe spreadsheet opening.
Network labels and errors redact userinfo, tokens and signed-URL parameters
without mutating the URL passed to libVLC. The complete system-interpreter suite
passes 319 tests in under the required 60-second ceiling.

### Installed package refresh

The root README is now a concise German operator guide instead of a long mixed
audit narrative. All four RC8 Debian packages were rebuilt from the current
tree, checksum-verified and installed system-wide. Installed-path acceptance
covers the CLI, a real native encode/verify/export A/V roundtrip, desktop files,
web scripts and real Tk construction of MPCASU and the converter. That GUI smoke
found a mini-player restore callback race; the sibling pack order was corrected,
the 10-test Xvfb group passed, and all packages were rebuilt and reinstalled.

### Bidirectional conversion and web player

The converter now has a verified reverse path. `casu export` and the graphical
From-CASU mode accept sidecars, CASUNAT1 and CASUNAT2. Sidecars resolve and
SHA-256-check their recorded source; CASUNAT1 verifies and extracts the original
payload; compatibility sources map all A/V/text/chapter tracks, while CASUNAT2 reconstructs all native video/audio streams, text/rich ASS
subtitles and chapter tables from key states, tile updates and timestamped PCM before
FFmpeg writes the requested extension. Single files, multiple selections and
recursive folder queues are covered. Source-deletion acceptance tests confirm
A/V output, two audio tracks, text and styled ASS subtitles, and two chapters
after export. The default native bitmap subtitle track is alpha-composited only
during its active interval, providing a portable MP4/MKV burn-in without
claiming an editable PGS/DVD/DVB/XSub remux. A compatibility-sidecar matrix likewise retains video, two audio
tracks, text subtitles and chapters.

MPCASU now recognizes YouTube watch/share URLs, resolves them outside the Tk
thread through `yt-dlp` to one combined direct stream and then uses the existing
libVLC network path. Direct stream URLs are unchanged. The responsive-layout
handler now ignores descendant Configure events, preventing simultaneous full
and compact navigation, and advanced media controls occupy a separate row so
they remain reachable at desktop widths.

Audio-only presentation now asynchronously extracts a bounded measured PCM
waveform (FFmpeg for legacy sources, native PCM blocks for CASUNAT2) and draws a
position cursor. It no longer presents the formerly open placeholder; generated
legacy and source-independent native waveform tests confirm nonzero sample data.

The desktop player now has a real mini-player transition rather than a second
playback implementation. It retains the active backend, hides library/queue and
diagnostics, uses a compact transport window with an always-on-top hint, and
restores the prior geometry and responsive panels via the Mini button or `N`.
A real Tk/Xvfb transition/restore test passes.

The new dependency-free `web/` player was rendered in Chromium against the
supplied red MPCASU reference. It implements local multi-file and drag/drop
playback, direct streams, transport-controlled YouTube embedding, M3U/M3U8/PLS
import, local SRT/WebVTT sidecars, search/reorder, seek, volume/mute,
shuffle/repeat, fullscreen and picture-in-picture. JSON
sidecars verify a co-selected source and CASUNAT1 verifies/exposes its payload
entirely in-browser. CASUNAT2 now verifies header/chunk flags and bounds, typed
stream topology and configs, complete per-chunk hashes and seek-key coverage in
addition to its integrity prefix, then reconstructs
selectable native video/audio streams from deflated key states, tile updates
and s16le PCM. Native text and verified lossless RGBA bitmap cues render
against the playback clock and chapter entries seek to their stored nanosecond
PTS. It also applies explicitly keyed video format changes. Reproducible
Chromium smokes switch the second of two video, audio and subtitle tracks,
decode a bitmap cue and chapter, exercise the automatic legacy fallback, and
load a real local SRT cue. Browser libass styling remains a text fallback; a
cumulative 512 MiB decoded-media ceiling prevents unbounded
browser preloading. Desktop native CASUNAT2 playback is unchanged.

The installed loopback launcher now closes the browser-codec gap rather than
merely displaying a decode error. The UI automatically retries an explicitly
selected local file through bounded temporary FFmpeg transcoding, choosing
VP9/Opus WebM or H.264/AAC MP4 from the browser's advertised support. Local
fallback output has byte-range seeking. Explicit network URLs can be probed and
served as a cancellable fragmented stream; local/pseudo-protocol URLs are
refused and credentials are redacted in returned errors. A real Chromium UI
test proves automatic fallback for unsupported rawvideo/PCM NUT, and a
16-format generated input matrix plus finite HTTP-source test covers the shared
server path. Temporary uploads and products are removed on launcher shutdown.
The loopback handler rejects DNS-rebinding hosts and cross-origin mutations and
ships a restrictive CSP plus frame, referrer and permissions headers.

Clean temporary Debian builds include both new Python modules and the web app;
the MPCASU package declares `yt-dlp`. A clean no-isolation wheel build/install
contains the same files and passes its installed CLI smoke.

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

The revision-2 format contract is now enforced at both write and read time.
One `CasuLimits` model bounds file/manifest/stream/chunk/decoded-resource and
JSON complexity; strict JSON rejects duplicate keys and non-finite values.
Unique typed stream descriptors are repeated as canonical matching
`STREAM_CONFIG` chunks. Chunk type/stream identity, PTS order, singleton
structures, complete seek-key coverage, exact per-chunk hashes and decoded
payload semantics must all agree before full verification succeeds. Dynamic
video format changes are explicit and immediately followed by a complete key
state, retaining bounded random access across geometry changes.

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
Recovery points now authenticate the complete preceding byte prefix and their
own declaration before recovery exposes the boundary. The writer also bounds
total output size, fsyncs the completed file and containing directory, and only
then atomically replaces the destination. The strengthened seed-20260813
10,000-case run rejected 9,986 inputs, accepted 14 still-valid inputs and had
zero unexpected outcomes in 3.0 seconds.

### Gate 5 — Media/converter product core: PARTIAL

The converter is now also a general full media converter. `casu transcode` and
the GUI's default `media-to-media` direction accept a single file, multiple
files or recursive folder trees and use the same `ConversionEngine` as CASU
creation. Explicit output support covers common modern and legacy audio/video
containers; automatic container-compatible codecs, remux/balanced/high/small/
lossless profiles, first/all-track selection, subtitle handling and metadata/
chapter preservation are shared by CLI and GUI. FFmpeg writes an adjacent
temporary target, progress is parsed monotonically, cancellation terminates the
child and removes the partial, and a successful file is probed for a playable
stream before atomic replacement. A generated reference matrix passes every
advertised target extension (14 audio and 18 video), including multiple audio tracks, subtitle,
title and chapter preservation and a normalized legacy FLV sample-rate edge.

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

## 2026-08-13 — File operation hardening

All user-facing file selection is now content-routed where CASU identity
matters. Desktop and CLI folder batches reject symlink escapes, cap eligible
inputs, preserve relative layout and prevent source/output collisions.
Playlist, settings, session, report and journal JSON uses bounded reads and
atomic durable replacement. Web playlists are bounded by bytes, lines and
entries, while interrupted uploads and unpublished transcode outputs are
removed immediately. Recursive CLI discovery walks before sorting its bounded
accepted set. The complete isolated-X regression suite passes 328 tests with 6
opt-in corpus skips in 57.05 seconds.
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
