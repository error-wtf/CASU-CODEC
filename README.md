<!-- SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4 | SPDX-FileCopyrightText: 2026 Lino Casu -->
# CASU Codec / Container

**License:** All Rights Reserved / Anticapitalist License 1.4 by Lino Casu.
See [`LICENSE`](LICENSE). Third-party components retain their own licenses.

**CASU** means **Codec for All Segmented Units** in this project. “Casu” also
preserves the author's surname and is the `.casu` container/sidecar identity.
CASU is a conservative segmented-state codec/container project. **MPCASU** is
its media player. This repository is currently a release candidate under active
gate development; it is not a finished native 1.0 product.

The core abstraction is:

\[
\boxed{\text{State}+\text{Segment}+\text{Change}+\text{Timing}}
\]

rather than treating a media stream as only `Frame + Frame + Frame`. The
legacy decoded stream remains authoritative; CASU records where a state holds,
what changed and which source timestamps govern presentation.
It accepts ordinary media through established decoder infrastructure. The
legacy sidecar and CASUNAT1 compatibility paths keep the original media as the
source of truth. CASUNAT2 is the standalone segmented-container path: its
key states, exact tile updates, source PTS and canonical PCM survive deletion
of the input. CASUNAT1 is never presented as a substitute for it.

This repository is a new implementation informed by the supplied SSC briefs.
The original prototype is preserved unchanged as
[`legacy_ssc_codec_v01.py`](legacy_ssc_codec_v01.py); the reference documents
are copied into `docs/` for provenance and are not modified.

## Current command-line slice

```bash
python3 -m pip install -e .
casu analyze /path/to/movie.mp4
casu analyze /path/to/song.mp3
casu convert /path/to/movie.mp4 --output movie.casu
casu pack-v2 /path/to/movie.mkv --output movie.casu
casu convert /path/to/movie.mkv --container native-v2 --output movie.casu
casu convert /path/to/folder --container native-v2 --output /path/to/output --retry 1 --resume
casu benchmark /path/to/movie.mp4 --output benchmark.json
casu verify movie.casu
casu info movie.casu
```

Conversion supports three explicit policies. `--mode strict` uses the real
source-resolution decoder and exact native-plane tile identity with rational
source PTS. It has no FPS filter, downscale, threshold, SSIM, or hidden color
conversion. `--mode visually_lossless` and `--mode adaptive` still use the
separate reduced activity-preview analyzer and are experimental hints; they do
not provide STRICT fidelity.

STRICT prefers the optional library-level PyAV/libav adapter when installed
(`pip install 'casu-codec[libav]'`) and otherwise uses the tested FFmpeg CLI
adapter. Both adapters preserve active native planes and decoded presentation
PTS; neither uses an FPS filter. The fallback remains supported for minimal
distribution packages while the library adapter gains wider platform coverage.
FFprobe inventories run through a shared monitored runner with explicit output
and time budgets; decoded STRICT frames also have dimension and byte ceilings.

The `mpc` command remains a CLI compatibility alias. Playback belongs to the
separate `mpcasu` application.

Launch the first MPCASU player prototype:

```bash
mpcasu /path/to/movie.mp4
```

MPCASU has two explicit playback paths. Ordinary media, URLs, sidecars and the
CASUNAT1 compatibility envelope use the installed libVLC shared library in
process. There is no extension allow-list: if the installed libVLC build and
its modules can open a source, MPCASU passes it through. Exact codec support is
therefore a runtime fact, not a hard-coded marketing list. CASUNAT2 uses the
independent `NativeCasuBackend`: it seeks to byte-indexed key states, applies
tile dependencies, presents reconstructed frames to the Tk video sink and
writes s16le blocks directly through libpulse-simple. It neither inherits the
libVLC backend nor creates a temporary MP4.
Rapid seeks serialize worker transitions; a blocked old PCM write must stop
before cache invalidation, sink flush and a new generation can start. A timeout
fails closed instead of allowing stale audio to cross the seek boundary.
Live audio/video/subtitle track changes use the same transactional boundary.
They restart at the measured media position, discard queued output, clear the
old subtitle and reopen PulseAudio when the new track changes sample rate or
channel geometry.
Transient native decode/output failures also invalidate queued presentation,
flush PCM, reset the master clock and retain a bounded concrete error message.
The same open CASUNAT2 container can then replay from the recorded failure
position without extraction or backend reconstruction.
Full subtitle/chapter/device models and SQLite scan/resume/favorites/playlists
now exist as a tested shared core;
atomic playback settings and dynamic track/output/chapter menus are also implemented.
The sidebar and queue are synchronized views of one bounded, duplicate-free
playlist model used by navigation, session persistence and playlist files.
Converter CLI and GUI share monotonic batch progress, measured elapsed time,
throughput ETA and per-result conversion duration from the same job engine.
Both expose retry behavior; the GUI includes a bounded detailed view of the
last batch report. Completion and cancellation reports are validated and
published atomically; a cancelled batch records verified completed jobs and
the cancelled remainder instead of presenting a partial run as complete.
Library search and watched-folder rescans are wired to the persistent SQLite
core. Per-media audio/video/subtitle selections and audio/subtitle delays are
persisted and restored. Source-stat-versioned thumbnails decode asynchronously
through FFmpeg. Attached pictures are normalized into bounded, hashed CASUNAT2
`cover-art` attachments, displayed by the native audio player and reused by the
library after the source is deleted. Real PNG, JPEG and WebP attached-picture
inputs pass this source-deletion path. Cover decoding fails closed for missing,
non-positive or oversized geometry (8192 pixels per axis and 256 MiB decoded
RGBA budget). Bounded container/stream tags and complete
demuxer dispositions are retained in the standalone manifest. ASS/SSA sources
retain their bounded, hashed stylesheet/dialogue payload and the native player
renders it through system libass into a transparent RGBA overlay; a plain-text
fallback remains when libass rejects a document. Bounded embedded TTF/OTF/font
attachments are registered with the same renderer before font selection.
PGS, DVD, DVB and XSub bitmap subtitles convert to bounded, hashed RGBA regions
and remain selectable/seekable native subtitle overlays after source deletion.
Broader malformed, language and platform cases remain. Hardware A/V
drift evidence and release
playback matrices remain open gates.
Native PCM timing uses measured PulseAudio sink latency when available and a
monotonic fallback otherwise. Native audio supports real 0.25×–4× playback by
deterministically resampling interleaved s16le PCM while keeping the sink at its
hardware sample rate; the audio clock converts latency and wall time back into
media time at the active rate. This is speed/pitch resampling, not a claim of
pitch-preserving time-stretch.
Clock observations are anchored to absolute PCM PTS, never accumulated block
deltas. They cannot move media time backwards when reported latency changes,
and non-finite, negative or over-60-second driver values are ignored. A
21,600-block/six-hour simulation at 1.5× has zero cumulative timing drift;
physical-device evidence remains a separate open gate.
Backend-reported chapters appear both in the dynamic chapter menu and as
clickable, exact-position markers below the seek timeline.

The same atomic, journaled job engine is also available through a small Tk
interface. It supports recursive queues, pause/cancel, per-file failure
isolation, hash-verified journal resume, verification and machine-readable
batch reports with explicit `COMPLETE`/`CANCELLED` state:

```bash
casu-converter
```

The player is deliberately a separate application layer:

```text
film.casu → CASU codec/container → MPCASU player → audio/video output
legacy MP4/MP3/MKV ───────────────────────────────→ MPCASU fallback
```

The CLI `play` command intentionally rejects external playback and directs the
user to MPCASU. `analyze --mode strict` decodes active samples at source
resolution and writes a rational-PTS tile state map. Non-STRICT modes use the
explicitly labelled activity preview. Neither path retimestamps the source.

## Compatibility contract

- MP4/MP3 bytes, timestamps, codec metadata and A/V ordering remain canonical.
- State labels are scheduling hints only; they never authorize timeline changes.
- No interpolation, time-stretching, pitch shifting, scene invention or hidden
  colour/HDR changes are performed by this first slice.
- Uncertainty falls back to the full-fidelity legacy path.
- A sidecar is optional and can be deleted without making the media unplayable.
- A CASUNAT2 file is standalone; acceptance tests delete its source and then
  reproduce every video digest and the complete canonical PCM digest.

STRICT video canonicalizes padding-free active RGB/YUV/alpha planes, preserves
8/10/12/16-bit samples and relevant color metadata, and records exact
`pts/time_base` validity bounds. A tile is `HOLD` only when its complete
canonical identity is byte-identical; stream start and format changes produce
`KEY_STATE`. The reduced 160×90 Gray8 video analyzer and decoded PCM RMS audio
analyzer are activity hints only. `casu validate --verify-source` additionally
resolves legacy sidecar media and checks its SHA-256 digest.

## Test media

The repository includes owner-authorized reference fixtures in `test_media/`.
They are uploaded only as deterministic local test inputs; they are not claims
of independent scientific evidence. The supplied `/home/error/Videos/giancarlo.mp4`
remains an additional local validation asset and is intentionally not copied
into Git. To analyze it, run

```bash
python3 -m casu analyze /home/error/Videos/giancarlo.mp4 \
  --output artifacts/giancarlo.mp4.casu
```

The generated artifact is ignored by Git because media-derived caches should be
reproducible rather than silently committed. The bundled fixtures have checked
SHA-256 values in [`test_media/README.md`](test_media/README.md), and their
portable CASU manifests are generated by the same converter used in production.

## Gate roadmap

The binding implementation order is documented in
[`ROADMAP_60_STEPS.md`](ROADMAP_60_STEPS.md). The short form is:

1. source-resolution STRICT;
2. standalone CASUNAT2 payload and byte-offset seek;
3. integrity, recovery, limits, and fuzzing;
4. native CASU playback without legacy extraction;
5. converter engine, media management, library/settings, responsive UI;
6. full playback/build/package regression before a stable 1.0 claim.

See [`docs/FORMAT_SPEC.md`](docs/FORMAT_SPEC.md),
[`docs/CASU_FORMAT_SPEC.md`](docs/CASU_FORMAT_SPEC.md),
[`docs/CASU_CONVERTER.md`](docs/CASU_CONVERTER.md),
[`docs/VALIDATION.md`](docs/VALIDATION.md),
[`docs/PLAYER_PROVENANCE.md`](docs/PLAYER_PROVENANCE.md),
[`docs/LEGACY_MEDIA_REQUIREMENTS.md`](docs/LEGACY_MEDIA_REQUIREMENTS.md) and
[`docs/DEVELOPMENT_PATH.md`](docs/DEVELOPMENT_PATH.md).
Historical release-note drafts are not release evidence. Current evidence is
recorded in `RELEASE_GATE_STATUS.json`, `IMPLEMENTATION_REPORT.md`, and
`TEST_REPORT.md`.

## Upstream foundations and research boundary

Legacy playback follows the public [VLC/libVLC](https://github.com/videolan/vlc)
embedding model and its [media-player API](https://videolan.videolan.me/vlc/master/group__libvlc__media__player.html).
Source probing/decoding follows [FFmpeg's timestamp rules](https://ffmpeg.org/ffmpeg.html)
and deliberately avoids output `-r`/FPS filters in STRICT. The supplied
[Webamp embed](https://github.com/error-wtf/webamp-embed),
[MP3 codec](https://github.com/ggrandes-clones/mp3_codec),
[LAME](https://github.com/lameproject/lame), and
[libde265](https://github.com/strukturag/libde265) repositories were treated as
architectural/licensing research, not copied into CASU. Their licenses remain
independent; CASU does not claim their implementations as its own.

## Status

`CASU 1.0.0rc8 · DEVELOPMENT / RELEASE CANDIDATE · GATES OPEN`

This is a media-systems experiment. A passing analyzer test is not evidence of
display-power savings or a physical claim about human perception.
