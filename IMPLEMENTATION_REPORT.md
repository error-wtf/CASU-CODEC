# Implementation report

## 2026-08-08

### Gate 2 — Source-resolution STRICT: PARTIAL

Implemented `casu.strict` with:

- immutable multi-plane canonical frames;
- 8/16-bit plane validation;
- source PTS/time-base model;
- exact per-plane tile hashing;
- chroma/alpha-sensitive HOLD vs UPDATE decisions;
- monotonic PTS validation and state-map intervals.

Evidence: strict unit tests cover identical frames, one changed plane sample,
16-bit planes and PTS-derived timestamps.

Still open for PASS: a production demux/decoder adapter that supplies native
source-resolution planes and true source PTS for YUV420/10-bit, VFR, B-frames,
alpha and color metadata from real media. The existing 160×90 grayscale path
remains an activity hint and is not used as proof of STRICT identity.

No 1.0 release claim is made while this gate is PARTIAL.
