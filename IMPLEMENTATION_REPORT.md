# Implementation report

## 2026-08-08

### Gate 2 — Source-resolution STRICT: PARTIAL

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

### Gate 1 — Native CASUNAT2 payload: PARTIAL

Implemented `casu.native_v2` as a standalone deterministic binary container
primitive with typed chunks, atomic writing, key-state/update byte offsets,
seek-index serialization, bounded reads and SHA-256 integrity verification.
It now also serializes lossless canonical video key-state planes and
subsampled-plane tile updates, with a reconstruction cache. The source file is
not required to read the written chunks.

Still open for PASS: audio/subtitle/chapter chunk semantics, recovery-point
recovery validation across truncated files, native player/audio sinks and
end-to-end codec roundtrip fixtures against real media.

Lossless timestamped CASUNAT2 audio blocks are now implemented with explicit
sample rate, channel layout, sample format, sample count and PTS metadata.

### Gate 6 — Integrity/recovery/resource limits: PARTIAL

CASUNAT2 now writes periodic recovery-point chunks and the reader enforces
manifest, chunk-count, chunk-size and total-file limits while validating
truncation, chunk types, recovery offsets and SHA-256 integrity. Fuzzing and a
complete corrupt-file corpus remain open.
