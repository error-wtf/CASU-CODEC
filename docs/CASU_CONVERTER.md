<!-- SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4 | SPDX-FileCopyrightText: 2026 Lino Casu -->
# CASU converter

The converter never modifies its input. It exposes three distinct outputs:

- `sidecar`: JSON analysis that resolves and verifies the original source;
- `native`: CASUNAT1 compatibility envelope containing the original bytes;
- `native-v2`: standalone CASUNAT2 key-state/tile/PCM media.

```bash
casu convert input.mp4 --output input.casu
casu convert input.mp4 --container native --output input-v1.casu
casu convert input.mkv --container native-v2 --output input-v2.casu
casu convert media-folder --container native-v2 --output converted --retry 1 --resume
casu pack-v2 input.mkv --output input-v2.casu --tile-size 64 --key-interval 3
casu verify input-v2.casu
casu info input-v2.casu
casu repair-v2 damaged.casu --output recovered.casu
```

The CLI and GUI `casu-converter` use the same `ConversionEngine`, job and
profile model. The engine provides atomic output, an atomic JSON journal,
per-file failure isolation, progress, cancellation, retry (CLI) and resume
only after the output size/SHA-256 and exact prior job/profile list match. The
GUI adds recursive queues, pause/cancel and batch verification. Video is decoded
in presentation order at source
resolution. Complete key states and exact plane-aware tile updates retain the
source pixel format, active samples, color metadata and rational PTS. Audio is
decoded to timestamped interleaved s16le PCM blocks with sample rate, channel
count/layout and sample count. Text subtitles become timestamped UTF-8 packets
and chapters use a 1/1,000,000,000 time base. The source pathname is not stored
in the native payload contract. File attachments are bounded and SHA-256
verified. Embedded album pictures are decoded once to PNG and stored with role
`cover-art`; an audio file with a cover therefore remains audio-only and its
cover survives source deletion. Container/stream tags and the complete demuxer
disposition map are canonicalized under explicit count/value/total-byte limits.
ASS/SSA streams additionally retain their complete bounded source document as a
`subtitle-source` attachment. Native playback renders it through libass at media
time and falls back to the generated UTF-8 packets if loading/rendering fails.
Recognized attached fonts receive role `subtitle-font` and are registered under
aggregate/per-font/name limits before libass renderer creation.
PGS/DVD/DVB/XSub streams use FFmpeg's decoded bitmap-to-video boundary, coalesce
duplicate timestamp states, discard transparent HOLD states and store only each
nontransparent alpha bounding rectangle as a lossless `SUBTITLE_BITMAP` chunk.

`--mode strict` is the reference sidecar analysis engine. It performs exact
source-resolution native-plane comparisons. `visually_lossless` and `adaptive`
remain reduced activity hints and make no pixel-identity claim.

CASUNAT2 writes atomically. Its reader verifies header/version, declared
lengths, chunk types, byte-offset seek entries, recovery-point structure and a
SHA-256 integrity footer and per-chunk hashes. Video and audio decompression
have explicit decoded byte limits. `repair-v2` finalizes only the last
writer-declared complete prefix and labels the output `RECOVERED_PREFIX`.

The sidecar manifest still records source path, filename, size and SHA-256;
`validate --verify-source` fails closed when those no longer match. CASUNAT1
may be extracted by the libVLC compatibility backend. CASUNAT2 is decoded
directly by `NativeCasuBackend` and never extracted to a legacy media file.
