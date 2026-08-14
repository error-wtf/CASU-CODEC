# CASU Converter deep audit — updated 2026-08-13

## Executive result

The repository now has a real source-to-CASUNAT2 converter, not only a sidecar
analyzer. CLI and GUI submit the same `ConversionJob`/`ConversionProfile`
objects to `ConversionEngine`; the engine calls the production native-v2
converter and writes an atomic progress journal. The CLI additionally exposes
`pack-v2`, `verify`, `repair-v2`, `info`, `export` and the general
media-to-media `transcode` command. The GUI exposes the same full conversion
direction as its default.

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
| Atomic output/cancel cleanup | PASS reference path | Engine cancellation is fail-closed and journaled; typed partial-result evidence and atomic CANCELLED reports pass engine and real Tk/Xvfb GUI tests. |
| Subtitle/chapter/attachments | PASS reference matrix | Text, ASS/SSA libass+font and typed PGS/DVD/DVB/XSub bitmap paths pass source deletion; chapters, attachments, bounded metadata and PNG/JPEG/WebP covers pass. Cover decode has explicit geometry/memory ceilings. |
| Batch queue/retry/journal | PASS core | Recursive GUI/CLI queues preserve subfolders, disambiguate equal explicit filenames, isolate failures, retry, and resume only collision-resistant hash-verified journal entries. CLI and GUI both batch CASU→media exports. |
| General media conversion | PASS advertised-output matrix | Shared-engine CLI/GUI media-to-media jobs provide atomic verified publication, cancellation, retry/resume, five profiles, explicit codecs, compatible all-track mapping and metadata/chapter preservation. Generated tests pass all 14 advertised audio and 18 advertised video extensions. |
| Progress/ETA/reports | PASS reference path | Shared monotonic batch progress exposes per-job/overall fraction, measured elapsed time, throughput ETA and state. Bounded atomic JSON/CSV/Markdown reports retain source/output/profile hashes, tool versions, frame/key/tile/hold/audio/subtitle counts, verification, warnings and duration. |
| Hostile-input budgets | PARTIAL | Reader/decompression limits plus centrally monitored 30-second/64-MiB FFprobe output and decoded-frame dimension/byte ceilings exist; broader decoder/corpus stress remains. |
| Stable release | OPEN | Package remains `1.0.0rc8`. |

## Remaining converter work

1. Calibrate the implemented bounded report/filter/export view on very large
   heterogeneous production batches; the required JSON/CSV/Markdown metrics
   and exact 17-valid/3-corrupt 20-file isolation acceptance already pass.
2. Expand the working typed PGS/DVD/DVB/XSub path across platforms and malformed
   libass ASS/SSA, text fallback, chapters/attachments, PNG/JPEG/WebP artwork, bounded tags
   and complete dispositions already pass.
3. Calibrate the working measured-throughput ETA across long heterogeneous
   batches; recursive jobs, retry/isolation and machine-readable durations are implemented.
4. Expand the existing probe/frame resource budgets with a corrupt decoder
   corpus and long-media tests.
5. Expand the clean installed Debian converter matrix beyond the generated
   reference corpus and Linux/FFmpeg version currently tested before 1.0.

No energy saving or perceptual-quality result is inferred from conversion.
