# casu_core — Shared Library Roadmap (CASU formats)

Purpose: single, integrity-first implementation of the CASU container family,
used by all tools (never per-tool duplication). Reference:
`casu/` (core, schema, native, native_v2, mp5, filetypes, tiles, tags,
scheduler) + research/casu-format-deep-dive.md.

## WP-CORE-001 Container primitives
- Magic/header structs (CASUNAT1 92B, MP5), bounded byte I/O, typed errors
  (CasuError/NativeCasuError/Mp5Error), no path traversal.
- UNIT: header round-trips, truncated/corrupt input. STATUS: VERIFIED (formats.hpp/cpp, sha256).

## WP-CORE-002 Manifest parse/validate + limits
- schema validation; limits (manifest ≤64 MiB, payload ≤16 GiB, chunk ≤64 MiB,
  chunks ≤1M, streams ≤64). UNIT: valid/invalid manifests. STATUS: VERIFIED (json.cpp, manifest.cpp).

## WP-CORE-003 CASUNAT1 read/write + payload verify/extract
- 92B header, JSON manifest, byte-exact payload, sha256. UNIT + golden.
  STATUS: VERIFIED (native.cpp; golden PASS demo_clip.mp4.casu).

## WP-CORE-004 CASUNAT2 reader
- segmented key-state/tile-update/PCM chunks, per-chunk integrity.
  UNIT + golden. STATUS: VERIFIED (native_v2.cpp; integrity/seek/recovery; golden PASS demo_casunat2.casu).

## WP-CORE-005 MP5 reader/writer
- chunk types, zstd(+zlib fallback), footer(36B) digest, attachment
  extract/verify. UNIT + golden. STATUS: VERIFIED (mp5.cpp; zlib; golden PASS demo.mp5).
  (zstd-Pfad: siehe WP-CORE-007/BLOCKER-001.)

## WP-CORE-006 Sidecar resolve + metadata/tags/tiles/scheduler helpers
- resolve source by size+sha256; tags, tiles, scheduler structures.
  STATUS: NOT_STARTED.

## WP-CORE-007 zstd integration
- libzstd; compress/decompress/corrupt/empty/large. Not reimplemented.
  STATUS: VERIFIED (2026-08-18). libzstd 1.5.7 MinGW aus Quelle gebaut
  (BLOCKER-001 gelöst); mp5.cpp `decompress`: zstd zuerst → zlib-Fallback
  (Referenz reader.py:47); Writer bleibt zlib (byte-identische Golden-Fixtures).
  Unit unter Wine grün (zstd-Roundtrip, korrupter Payload → CasuError).

## WP-CORE-008 Golden fixtures
- Generate from reference (Linux) into tests/golden; byte vs semantic compare
  documented per format. STATUS: NOT_STARTED (Golden-Vergleiche laufen bereits
  via fixtures/ + cli + manuelle Protokolle; Formalisierung in tests/golden/
  steht aus).

## Compatibility gate
Windows casu_core output == Linux reference (byte where required, semantic
otherwise). Wine: run unit tests under Wine too.
