# CASU codec deep audit — 2026-08-08

## Executive result

The repository currently contains a careful **legacy sidecar analyzer** and
some standalone tile-comparison primitives. It does not yet contain a codec or
container runtime. Calling the current output a native CASU file would be
incorrect.

## Capability matrix

| Area | Status | Evidence |
|---|---|---|
| Versioned format | PARTIAL | JSON identity uses `MPCASU\\0`, schema `0.2`, package version `1.0.0`; no native binary format version negotiation. |
| Native reader/writer | PARTIAL | `casu.native` now provides a versioned lossless envelope reader/writer with header, manifest/payload hashes and atomic output; segmented payload chunks and playback are still absent. |
| Standalone media | PARTIAL | Native envelope files embed original bytes; legacy JSON sidecars still depend on the original MP4/MP3 path. |
| Video codec preservation | MISSING | FFmpeg only emits reduced grayscale analysis frames; no video payload is encoded or copied into CASU. |
| Audio codec preservation | MISSING | Audio is downmixed to mono float PCM for RMS hints; no audio payload or channel-preserving stream exists. |
| Subtitle/chapter/attachment preservation | MISSING | Probe metadata is not written as native stream payloads; tags, chapters, fonts, cover art and attachments are lost. |
| Exact strict identity | MISSING in runtime | `casu.tiles` can compare canonical uint8 arrays exactly, but the production analyzer still uses 160×90 grayscale previews and never calls the tile engine. |
| Spatial state map | PARTIAL | `casu.tiles` emits in-memory tile records; no persistence, integration with decoded PTS, payload references or reader consumption. |
| Temporal truth | PARTIAL | Source duration is retained, but sampled frame intervals use requested analysis FPS rather than every source PTS/VFR timestamp. |
| Tile lifecycle | PARTIAL | Primitive records contain lifecycle/hash/region fields; scheduler consumes only global time intervals and ignores tile dependencies. |
| Key states | MISSING | `native_key_states` is explicitly `False`; no reconstruction checkpoints exist. |
| Seek index | PARTIAL | Sidecar segment-boundary hints exist; no byte offsets, key-state references or native random access. |
| Recovery | MISSING | No truncation recovery, journal, footer recovery or damaged-segment continuation. |
| Integrity | PARTIAL | Source size/SHA-256 and schema validation exist; no per-payload, index, segment checksum or signature. |
| Determinism | PARTIAL | State IDs and JSON output are stable in normal runs, but analysis depends on FFmpeg build/filter behavior and absolute source paths. |
| Scheduler/cache | PARTIAL | Indexed global interval lookup exists; no bounded tile cache, dependency graph, invalidation, release or deadline execution. |
| Safety limits | PARTIAL | Manifest bounds exist; decoded frame count, dimensions, duration, memory, output size and CPU/time budgets are not bounded. |
| API/library use | PARTIAL | Python functions are usable by CLI/tests; no stable public reader/writer/stream API. |
| Round-trip tests | MISSING | No native `source → CASU → decode` test can run because no native payload exists. |

## Concrete correctness gaps

1. `analyze_video` still creates activity hints from a reduced grayscale stream;
   even `strict` is explicitly not an identity proof.
2. `casu.tiles` accepts only canonical `uint8` arrays. Real media may use
   YUV planes, 10/12-bit samples, HDR transfer functions and pixel-aspect
   metadata; canonicalization for those formats is undefined.
3. The tile state map is in-memory only and is not consumed by
   `CasuScheduler`, `CasuBackend` or the converter.
4. State timestamps are derived from analysis cadence, not decoded PTS/DTS;
   variable-frame-rate and decoder-reorder behavior are therefore not modeled.
5. Segment validation checks ordering/overlap but not coverage, region bounds
   against stream dimensions, hash encoding, dependency validity or state-map
   continuity.
6. Audio analysis decodes only the first audio stream and downmixes it to mono;
   this cannot preserve multilingual, multichannel or bit-perfect audio.
7. The manifest stores only a limited stream-field subset and drops most
   metadata, chapters, subtitles, attachments and artwork.
8. `resolve_casu_source` verifies the external source but cannot verify a
   CASU payload because none exists.
9. The claimed package version `1.0.0` describes the sidecar compatibility
   release, not a native codec release. Native CASU should have an explicit
   format version and separate release gate.

## Required native architecture

```text
CASU header/version
  ├─ stream table (video/audio/subtitle/attachments)
  ├─ canonical timing table (source PTS/time-base)
  ├─ key-state chunks
  ├─ tile state/delta chunks
  ├─ payload chunks
  ├─ seek index (byte offsets + state references)
  ├─ integrity table/signatures
  └─ footer/recovery journal
```

The reader must reconstruct a requested timestamp from the nearest key state
and validated tile dependencies. The writer must reject unsupported fidelity
claims rather than silently down-convert source data.

## Codec release gates

CASU is not complete until all gates pass:

1. Canonicalization tests for 8-bit, 10-bit, planar YUV, alpha and HDR metadata.
2. Exact strict tile comparison integrated into decoded PTS-aware analysis.
3. Persisted `S(x,y,t)` state map with hashes, dependencies and key states.
4. Native binary reader/writer with standalone payload and random seek.
5. Per-stream audio/subtitle/chapter/attachment preservation.
6. Per-chunk/index/source integrity and damaged-file recovery tests.
7. Native round-trip tests comparing timing, frame/audio samples and metadata.
8. Fuzz tests and hard resource limits for malformed native files.

Until then, the honest product name is **CASU legacy sidecar/state-analysis
prototype**. The existing safety and validation work is useful foundation, but
it does not constitute codec completion.
