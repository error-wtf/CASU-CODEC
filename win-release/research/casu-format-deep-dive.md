# CASU Format Deep Dive (read-only analysis of `casu/`)

Ground truth: `casu/native.py`, `casu/native_v2/`, `casu/mp5/`, `casu/schema.py`,
`casu/core.py`. All formats are validated end-to-end; integrity is central.

## 1. CASU sidecar (legacy manifest, schema 0.2)

- JSON manifest file, magic string `"MPCASU\0"` in `format.magic`; extension `.casu`.
- Holds: source filename (basename only, no path traversal), optional source
  `sha256`, media metadata (streams, duration, size, tags), video/audio segment
  hints. Validation via `casu.schema.validate_manifest`.
- Playback: `resolve_casu_source` locates the original media next to the
  sidecar; size + sha256 must match. Browsers (pure-web) parse the same way.

## 2. CASUNAT1 (native container, rev 1)

- Magic `b"CASUNAT1"`, version 1.
- Header `struct "<8sHHQQ32s32s"` = **92 bytes**:
  - `8s` magic, `H` version, `H` reserved, `Q` manifest_length,
    `Q` payload_length, `32s` payload_sha256, `32s` (reserved/header digest).
- Layout: header | JSON manifest (≤64 MiB) | original media payload (≤16 GiB).
- Payload is byte-for-byte the original source; `payload_sha256` verified at
  open. Extraction writes a temp file (atomic rename), verifies on the fly.
- **Semantics: lossless embed + verified manifest.** Nothing lossy here.

## 3. CASUNAT2 (native v2, streaming segmented)

- `casu/native_v2/`: reader (543 lines), writer (201), validation (317),
  video (289), text (109), jsonutil (30).
- Segmented key-state / tile-update / PCM model with per-chunk integrity,
  decoded in-process by `mpcasu_native_backend.py` (no libVLC for the
  native path). Browser fallback exists in `casu-native.js` (pure-web).
- Status from tests: structure, index and SHA-256 verified per file.

## 4. MP5 (CASU MP5 container)

- Magic `b"CASUMP5\0"`, version 1. Header `"<8sHHII"` (magic, version, flags,
  manifest_length, reserved).
- Chunk header `"<BHII"` (chunk_type, stream_id, pts, comp_length).
- Chunk types: STREAM_CONFIG 0x01, VIDEO_KEY_STATE 0x10, VIDEO_TILE_UPDATE
  0x11, VIDEO_FORMAT_CHANGE 0x12, AUDIO_BLOCK 0x20, SUBTITLE_PACKET 0x30,
  SUBTITLE_BITMAP 0x31, CHAPTER_TABLE 0x40, ATTACHMENT 0x50, SEEK_INDEX 0x60,
  INTEGRITY_TABLE 0x70, RECOVERY_POINT 0x71, METADATA 0x80, END 0xFF.
- Payloads compressed with **zstd** (fallback zlib). Limits: 64 MiB chunk,
  1M chunks, 64 streams, ≤16 GiB file.
- **Footer (36 bytes):** `count(4) + sha256(32)` of the sorted compact JSON
  manifest → whole-container integrity check.
- Attachment chunks carry the original source (parts + filename + sha256);
  `extract_attachment` reassembles and verifies. This is the
  “verified source embedded” path used for fallback playback.

## 5. Integrity / limits summary (port to C++ must keep)

- SHA-256 everywhere (payload, manifest footer, attachments).
- Strict size caps: manifest ≤64 MiB, payload ≤16 GiB, chunk ≤64 MiB,
  chunks ≤1M, streams ≤64, XMLTV ≤32 MiB, playlists ≤8 MiB, sidecar ≤64 MiB.
- No path traversal in manifests (basename only).
- zstd primary compression, zlib fallback (keep both for compatibility).
- Errors are typed (`CasuError`, `NativeCasuError`, `Mp5Error`, …) and
  surfaced to the user, never swallowed.

## 6. Golden fixture plan

Generate from reference before porting:
- CASUNAT1: reference input → container → payload bytes + manifest hash.
- MP5: reference input → container → chunk table + footer digest + attachment.
- Sidecar: manifest JSON + resolved source.
Store under `tests/golden/`. Compare: byte-identical where required
(manifest digests, payload), semantically identical otherwise (streams).
