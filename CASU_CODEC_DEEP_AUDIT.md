# CASU codec deep audit — updated 2026-08-13

The authoritative live result is [`RELEASE_GATE_STATUS.json`](RELEASE_GATE_STATUS.json).
This audit distinguishes proved behavior from the remaining product gates.

## Current result

CASU now contains a real standalone native codec/container path. CASUNAT2 is
not CASUNAT1 renamed: it stores complete source-resolution canonical video key
states, exact hash-linked tile changes, source-timestamp timelines, canonical
PCM audio, a byte-offset seek index, recovery points and an integrity footer.
CASUNAT1 remains a compatibility envelope and JSON `.casu` remains a sidecar.

| Area | Status | Evidence / boundary |
|---|---|---|
| STRICT canonical video | PASS | RGB/YUV/alpha, 8/10/12/16-bit active planes, color metadata, VFR/B-frame presentation PTS and exact tile identity are media-tested. |
| CASUNAT2 reader/writer | PASS | Versioned typed chunks, atomic writer, verified byte offsets, integrity footer and bounded parsing. |
| Standalone video | PASS | Tests delete the source and reproduce every canonical frame digest. |
| Standalone audio | PASS | Timestamped s16le blocks reproduce the complete canonical PCM digest after source deletion. |
| Key states/tile dependencies | PASS | Start/interval keys plus base/new tile hashes; invalid dependencies fail closed. |
| Random access | PASS | Reader seeks to the nearest indexed on-disk key-state offset and reconstructs through target PTS. |
| Subtitle/chapter primitives | PASS reference matrix | Text and ASS/SSA+fonts render natively; typed alpha-bounded PGS/DVD/DVB/XSub RGBA conversion, source deletion and playback/seek pass. |
| Attachments/full metadata | PASS reference path | Bounded hashed files and attached covers survive source deletion; bounded tags and complete dispositions are retained. |
| Recovery/integrity | PASS release campaign | SHA-256, declared-prefix recovery, hostile limits/property fixtures and 3,000,000 deterministic mutations pass with 0 unexpected accepts/crashes/hangs. |
| Structural conformance | PASS generated adversarial matrix | Central limits, strict JSON, unique typed streams, canonical in-band configs, singleton chunks, ordered PTS, complete seek/hash coverage, semantic payload validation and explicit keyed format changes fail closed. |
| Native playback | PARTIAL | Direct video/PCM sinks and no-tempfile behavior pass; drift/device/subtitle matrices remain open. |
| Stable release | OPEN | Version remains `1.0.0rc8` until every product gate passes. |

## Implemented native architecture

```text
CASUNAT2 header + bounded manifest
  ├─ stream descriptors and rational frame timelines
  ├─ lossless VIDEO_KEY_STATE chunks
  ├─ hash-linked VIDEO_TILE_UPDATE chunks
  ├─ timestamped AUDIO_BLOCK PCM chunks
  ├─ subtitle/chapter payload primitives
  ├─ writer-declared recovery points
  ├─ validated byte-offset seek index
  ├─ SHA-256 integrity table
  └─ END marker
```

## Remaining blockers

1. Expand the passing PGS/DVD/DVB/XSub reference matrix across platforms,
   malformed streams and languages; complete the device/platform matrix.
2. Expand the strengthened bounded probe/parser campaign (10,000 cases,
   9,986 rejected, 14 verified, 0 unexpected) with larger decoder/network corpora.
3. Long-running A/V drift, rapid-seek and real audio-device matrix.
4. Complete the responsive UI and clean cross-platform package/runtime
   regression before stable 1.0.

The complete ordered work is in [`ROADMAP_60_STEPS.md`](ROADMAP_60_STEPS.md).
