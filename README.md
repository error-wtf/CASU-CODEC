# Casu Codec

**Casu** is a conservative, legacy-compatible segmented-state media layer. The `.casu` sidecar name is a Sardinian “cheese” reference: a compact, memorable media companion format, not a replacement for the original MP4/MP3 stream. The future VLC-/Winamp-inspired player built on this codec will be called **MPCASU**.
It accepts ordinary MP4 and MP3 files, keeps the original media as the source of
truth, and adds an optional temporal-state sidecar for future schedulers,
compositors and segmented displays.

This repository is a new implementation informed by the supplied SSC briefs.
The original prototype is preserved unchanged as
[`legacy_ssc_codec_v01.py`](legacy_ssc_codec_v01.py); the reference documents
are copied into `docs/` for provenance and are not modified.

## First working slice

```bash
python3 -m pip install -e .
casu analyze /path/to/movie.mp4
casu analyze /path/to/song.mp3
casu play /path/to/movie.mp4
casu play /path/to/song.mp3
```

`play` delegates to FFplay and does not transcode, retimestamp, stretch, or
otherwise modify the input. If a sidecar is missing or invalid, legacy playback
continues normally. `analyze` decodes a small inspection stream and writes
`movie.mp4.casu` or `song.mp3.casu`.

## Compatibility contract

- MP4/MP3 bytes, timestamps, codec metadata and A/V ordering remain canonical.
- State labels are scheduling hints only; they never authorize timeline changes.
- No interpolation, time-stretching, pitch shifting, scene invention or hidden
  colour/HDR changes are performed by this first slice.
- Uncertainty falls back to the full-fidelity legacy path.
- A sidecar is optional and can be deleted without making the media unplayable.

The current analyzer uses decoded luma activity for video and decoded PCM RMS
windows for audio. These are conservative temporal hints, not perceptual truth
and not a replacement for the source timestamps.

## Test video

The supplied `/home/error/Videos/giancarlo.mp4` is the first validation asset.
It is intentionally not copied into Git: run

```bash
python3 -m casu analyze /home/error/Videos/giancarlo.mp4 \
  --output artifacts/giancarlo.mp4.casu
```

The generated artifact is ignored by Git because media-derived caches should be
reproducible rather than silently committed.

## Roadmap

1. Timestamp-aware frame inventory and strict pixel-identical tile detection.
2. Tile state maps with HOLD/ADAPTIVE/REALTIME/LOSSLESS_REALTIME classes.
3. Seek-safe cache invalidation and full-frame fallback.
4. Reference-vs-segmented playback comparison and A/V-sync reports.
5. Optional visual state-display report; no native proprietary bitstream until
   the legacy path is independently validated.

See [`docs/FORMAT_SPEC.md`](docs/FORMAT_SPEC.md),
[`docs/LEGACY_MEDIA_REQUIREMENTS.md`](docs/LEGACY_MEDIA_REQUIREMENTS.md) and
[`docs/DEVELOPMENT_PATH.md`](docs/DEVELOPMENT_PATH.md).

## Status

`PROTOTYPE · LEGACY PLAYBACK AND ANALYSIS SLICE · REVIEW OPEN`

This is a media-systems experiment. A passing analyzer test is not evidence of
display-power savings or a physical claim about human perception.
