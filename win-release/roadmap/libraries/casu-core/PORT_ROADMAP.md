# casu_core — Shared Library Roadmap (CASU formats)

Purpose: single, integrity-first implementation of the CASU container family,
used by all tools (never per-tool duplication). Reference:
`casu/` (core, schema, native, native_v2, mp5, filetypes, tiles, tags,
scheduler) + research/casu-format-deep-dive.md.

## WP-CORE-001 Container primitives
- Magic/header structs (CASUNAT1 92B, MP5), bounded byte I/O, typed errors
  (CasuError/NativeCasuError/Mp5Error), no path traversal.
- UNIT: header round-trips, truncated/corrupt input. STATUS: NOT_STARTED.

## WP-CORE-002 Manifest parse/validate + limits
- schema validation; limits (manifest ≤64 MiB, payload ≤16 GiB, chunk ≤64 MiB,
  chunks ≤1M, streams ≤64). UNIT: valid/invalid manifests. STATUS: NOT_STARTED.

## WP-CORE-003 CASUNAT1 read/write + payload verify/extract
- 92B header, JSON manifest, byte-exact payload, sha256. UNIT + golden.
  STATUS: NOT_STARTED.

## WP-CORE-004 CASUNAT2 reader
- segmented key-state/tile-update/PCM chunks, per-chunk integrity.
  UNIT + golden. STATUS: NOT_STARTED.

## WP-CORE-005 MP5 reader/writer
- chunk types, zstd(+zlib fallback), footer(36B) digest, attachment
  extract/verify. UNIT + golden. STATUS: NOT_STARTED.

## WP-CORE-006 Sidecar resolve + metadata/tags/tiles/scheduler helpers
- resolve source by size+sha256; tags, tiles, scheduler structures.
  STATUS: NOT_STARTED.

## WP-CORE-007 zstd integration
- libzstd; compress/decompress/corrupt/empty/large. Not reimplemented.
  STATUS: NOT_STARTED.

## WP-CORE-008 Golden fixtures
- Generate from reference (Linux) into tests/golden; byte vs semantic compare
  documented per format. STATUS: NOT_STARTED.

## Compatibility gate
Windows casu_core output == Linux reference (byte where required, semantic
otherwise). Wine: run unit tests under Wine too.
