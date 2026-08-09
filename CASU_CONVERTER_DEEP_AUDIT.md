# CASU Converter deep audit — updated 2026-08-09

## Executive result

The repository now has a real source-to-CASUNAT2 converter, not only a sidecar
analyzer. CLI and GUI submit the same `ConversionJob`/`ConversionProfile`
objects to `ConversionEngine`; the engine calls the production native-v2
converter and writes an atomic progress journal. The CLI additionally exposes
`pack-v2`, `verify`, `repair-v2` and `info`.

```text
ffprobe stream/frame inventory
→ source-resolution presentation-order decode
→ canonical key states + exact tile updates
→ timestamped canonical PCM audio blocks
→ byte-offset seek index + recovery points + integrity footer
→ atomic CASUNAT2 replacement
```

| Capability | Status | Evidence / boundary |
|---|---|---|
| STRICT video decode | PASS | Exact source planes and rational PTS; VFR/B-frame/high-bit-depth fixtures pass. |
| Native CASUNAT2 output | PASS | CLI/GUI use the same production job engine and converter. |
| Standalone video/audio | PASS | Source-deletion digest round trips pass. |
| Multi-video/audio streams | IMPLEMENTED, matrix open | Stream descriptors and per-stream payload mapping exist; broad corpus pending. |
| Seek/verify/info | PASS | Real byte-offset validation and SHA-256 verification; CLI smoke passes. |
| Atomic output/cancel cleanup | PASS core | Engine cancellation is fail-closed and journaled; interactive GUI cancellation matrix remains. |
| Subtitle/chapter/attachments | PASS reference matrix | Text, ASS/SSA libass+font and typed PGS/DVD/DVB/XSub bitmap paths pass source deletion; chapters, attachments, bounded metadata and PNG/JPEG/WebP covers pass. Cover decode has explicit geometry/memory ceilings. |
| Batch queue/retry/journal | PASS core | Recursive GUI queue, CLI/GUI retry, per-file isolation and collision-resistant hash-verified journal resume are behavior-tested. |
| Progress/ETA/reports | PASS reference path | Shared monotonic batch progress exposes per-job/overall fraction, measured elapsed time, throughput ETA and state; JSON results retain conversion duration. Broader accuracy calibration remains. |
| Hostile-input budgets | PARTIAL | Reader/decompression limits plus monitored probe time/output and decoded-frame dimension/byte ceilings exist; broader decoder/corpus stress remains. |
| Stable release | OPEN | Package remains `1.0.0rc8`. |

## Remaining converter work

1. Expand the implemented GUI retry and bounded prior-run detail view with
   filtering/export for very large heterogeneous production batches.
2. Expand the working typed PGS/DVD/DVB/XSub path across platforms and malformed
   libass ASS/SSA, text fallback, chapters/attachments, PNG/JPEG/WebP artwork, bounded tags
   and complete dispositions already pass.
3. Calibrate the working measured-throughput ETA across long heterogeneous
   batches; recursive jobs, retry/isolation and machine-readable durations are implemented.
4. Expand the existing probe/frame resource budgets with a corrupt decoder
   corpus and long-media tests.
5. Run clean installed wheel/Debian converter and player matrices before 1.0.

No energy saving or perceptual-quality result is inferred from conversion.
