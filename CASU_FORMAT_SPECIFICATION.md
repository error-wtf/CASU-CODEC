<!-- SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4 | SPDX-FileCopyrightText: 2026 Lino Casu -->
# CASU release-candidate format specification status

CASU means **Codec for All Segmented Units** and uses `.casu`. Three explicitly
different representations currently coexist:

1. JSON sidecar (`MPCASU\0`, schema 0.2): analysis/provenance referencing the
   immutable source.
2. CASUNAT1: standalone compatibility envelope containing the original source
   bytes; it may be verified/extracted into the libVLC path.
3. CASUNAT2: standalone native segmented video/audio codec/container.

## CASUNAT2 layout

The big-endian CASUNAT2 header declares magic, version, flags and bounded JSON
manifest length. The manifest describes streams, source provenance without a
pathname, bounded container/stream tags, demuxer dispositions, rational time
bases and decoded frame timelines. Typed chunks follow:

```text
STREAM_CONFIG
VIDEO_KEY_STATE | VIDEO_TILE_UPDATE | VIDEO_FORMAT_CHANGE
AUDIO_BLOCK | SUBTITLE_PACKET | SUBTITLE_BITMAP
CHAPTER_TABLE | ATTACHMENT
RECOVERY_POINT
SEEK_INDEX
INTEGRITY_TABLE
END
```

A video key state contains every padding-free active canonical plane, pixel
format, source dimensions and color metadata. A tile update contains exact
plane regions and required base/result hashes. Audio blocks contain compressed
canonical s16le PCM plus PTS, time base, sample rate/count, channels and layout.
Attachments contain a safe basename, media type, bounded compressed bytes and
the SHA-256 of the decoded bytes. An attached-picture source stream becomes a
PNG attachment with role `cover-art`, not a synthetic video timeline. HOLD is
represented by state persistence: no redundant pixel payload is needed.
Every losslessly compressed payload declares its compression algorithm
(`zlib` in revision 2); unknown algorithms fail closed. A source format change
is represented explicitly by `VIDEO_FORMAT_CHANGE` and must be followed
immediately, for that stream, by a complete key state in the declared new
geometry/pixel format. The writer emits exactly one canonical `STREAM_CONFIG`
copy of every manifest stream descriptor.
ASS/SSA styling/dialogue documents may be retained as hashed attachments with
role `subtitle-source`; the native player renders the document at media time
through libass to a bounded transparent RGBA layer. The paired
`SUBTITLE_PACKET` stream is the fail-closed plain-text fallback.
Recognized bounded font attachments use role `subtitle-font`; consumers must
enforce per-font and aggregate budgets before passing them to a font engine.
`SUBTITLE_BITMAP` stores a 1/1000-timed RGBA alpha-bounding region, its canvas
geometry, decoded byte length and SHA-256. PGS/DVD/DVB/XSub conversion uses
FFmpeg's bitmap-subtitle `sub2video` path; transparent states end intervals
without being stored as invented video frames. The stream descriptor records
the canonical canvas; DVD subtitles use full-D1 PAL/NTSC coordinates even when
the associated video is half-D1 or VCD-sized.

Each seek entry stores a real file byte offset to a matching video key state and
the first dependency offset. A reader seeks there, validates stream/PTS/type,
then applies key/update chunks through the target PTS. The integrity SHA-256
covers every byte before `INTEGRITY_TABLE`; `END` is mandatory. Recovery exposes
only a writer-declared complete prefix, never arbitrary truncated bytes.

CASUNAT2 is source-independent. Acceptance removes the input and then compares
every canonical frame digest and the complete canonical PCM digest.

## Timing and fidelity

Source presentation PTS and rational time bases are authoritative. Silence,
static pictures and repeated states still occupy time. STRICT never uses an FPS
filter, resolution reduction, threshold, interpolation, retiming, pitch change
or hidden color conversion. Unsupported canonical layouts fail closed.

JSON sidecar state labels remain hints only. CASUNAT1 remains a compatibility
envelope and must never be advertised as CASUNAT2.

## Safety and current release boundary

Readers bound file, manifest, chunk count/size and decoded zlib output before
allocation; one public `CasuLimits` contract covers file/manifest/stream/chunk,
attachment, decoded-frame, dimension, channel/rate, dependency and JSON
depth/node budgets. Strict JSON rejects duplicate keys, non-finite numbers,
out-of-int64 integers and invalid Unicode. Readers validate manifest/stream
identity, chunk-to-stream type, singleton structures, PTS order, config
equality, every seek-key mapping, every per-chunk SHA-256, decoded payload
semantics, state hashes and the whole-prefix integrity digest. Unknown
versions/flags/compressors fail closed. Recovery points contain a hash-bound
checkpoint and prefix digest. The writer bounds total file size, fsyncs file
and containing directory, then atomically replaces the target. Source probes
have monitored byte/time budgets and decoded frames have dimension/byte
ceilings. The strengthened bounded 10,000-case parser campaign passes.
Signatures, broader malformed/language/platform subtitle fixtures and broader
platform/network stress remain open, so the product version stays
`1.0.0rc8`.

## Commands

```bash
casu analyze input.mp4 --mode strict
casu convert input.mp4 -o input.casu
casu pack-v2 input.mkv -o native.casu
casu convert input.mkv --container native-v2 -o native.casu
casu verify native.casu
casu info native.casu
casu repair-v2 damaged.casu -o recovered.casu
```

The detailed compatibility definition is in
[`docs/CASU_FORMAT_SPEC.md`](docs/CASU_FORMAT_SPEC.md); live gate evidence is in
[`RELEASE_GATE_STATUS.json`](RELEASE_GATE_STATUS.json).
