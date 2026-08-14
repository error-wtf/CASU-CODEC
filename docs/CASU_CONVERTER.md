<!-- SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4 | SPDX-FileCopyrightText: 2026 Lino Casu -->
# CASU full media converter

The converter never modifies its input. It supports three conversion directions:

- `media-to-media`: general FFmpeg media conversion;
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
casu export input-v2.casu --output restored.mp4
casu export album.casu --output restored.flac
casu transcode input.avi --output output.mp4 --preset high
casu transcode input.mkv --output repacked.mkv --preset remux
casu transcode media-folder --output webm-folder --format webm --preset small --retry 1 --resume --report transcode.json
```

General conversion accepts every input that the installed FFmpeg can decode.
The explicitly supported output set covers MP4/MOV/M4V/3GP, MKV/MKA, WebM,
AVI, MPEG/TS/MTS/M2TS, FLV/F4V, Ogg video, ASF/WMV and MP3/MP2/AAC/M4A,
FLAC/ALAC, WAV/AIFF, Ogg/Vorbis, Opus and WMA. Automatic container-compatible
codec selection is the default. `remux` copies streams, while `balanced`,
`high`, `small` and compatible `lossless` profiles encode them. By default all
compatible A/V/subtitle tracks, global/stream metadata and chapters survive;
`--first-tracks`, `--subtitles drop` and `--strip-metadata` opt out. Output is
written to a same-directory temporary file, probed for a playable stream and
atomically published only after success. Cancellation removes the partial file.

Reverse export verifies every CASU representation before writing media.
Sidecars resolve their hash-bound source and map all A/V/text/chapter tracks;
CASUNAT1 extracts its lossless source payload with the same mapping; CASUNAT2 reconstructs all native video key/tile streams, PCM,
text/rich ASS subtitles and chapter tables after the original source has been
deleted. FFmpeg chooses the destination container from the output extension;
containers without ASS support receive FFmpeg's compatible subtitle form.
The default (or first) native bitmap subtitle track is alpha-composited into
each active reconstructed video frame during reverse export. This portable
burn-in preserves its timing and appearance when the destination cannot carry
the original PGS/DVD/DVB/XSub codec, but it is intentionally not advertised as
an editable remuxed subtitle track. The GUI's `from-casu` direction applies one selected
format to single files, multiple selections or a recursive folder tree and
publishes the same bounded batch report.

The CLI and GUI `casu-converter` use the same `ConversionEngine`, job and
profile model. The engine provides atomic output, an atomic JSON journal,
per-file failure isolation, progress, cancellation, retry (CLI) and resume
only after the output size/SHA-256 and exact prior job/profile list match. The
GUI adds recursive queues, pause/cancel and batch verification. CASUNAT2 tile
size and periodic key-state interval are validated GUI profile controls; source
probing runs off the Tk thread with bounded FFprobe time and output.
It also exposes a validated 0–10 retry count and a bounded last-report table with
live text/status filtering and atomic filtered CSV and Markdown export.
Spreadsheet formula prefixes in text fields are escaped during CSV export.
Per-file source/output hashes, profile hash, tool versions, frame/key/tile/hold,
audio/subtitle counts, verification result, warnings, attempt count and elapsed
time remain available in JSON/CSV/Markdown evidence. Reports are
validated and atomically published with an explicit `COMPLETE` or `CANCELLED`
state; cancellation retains evidence for already verified jobs and identifies
the uncompleted remainder.
The engine emits monotonic `ConversionProgress` events with job/batch fraction,
measured elapsed time, throughput ETA and state. GUI and machine-readable
results consume this shared timing; completed results retain conversion seconds.
Video is decoded in presentation order at source resolution. Complete key
states and exact plane-aware tile updates retain the
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
The converter supplies the canonical stream canvas explicitly; DVD half-D1/VCD
video therefore cannot truncate full-D1 PAL/NTSC subtitle coordinates. A
malformed secondary stream with no decodable format is recorded in
`ignored_streams` while independently valid A/V/subtitle streams still convert.

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
