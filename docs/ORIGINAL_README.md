# SSC v0.1 — Segmented State Codec prototype

SSC is a research prototype for the idea discussed in this chat: **treat persistent state and actual change as the fundamental unit instead of blindly treating every global display tick as equally important**.

It accepts existing `.mp4` and `.mp3` files, so old data systems can feed it. It does two things:

1. **Temporal-state analysis** — writes a `.ssc.json` sidecar containing static/low-motion/motion regions in time for video and silence/low-level/active regions for audio.
2. **Legacy-compatible optimization** — creates a normal playable output using FFmpeg while preserving source timing. For MP4 it can optionally collapse duplicate/near-duplicate frames into variable-duration holds; for MP3 it can either copy the MP3 bitstream unchanged (`compat`) or transcode to a lower-bitrate Opus stream (`efficient`/`max`).

This is **not yet a new ISO media bitstream**. It is the compatibility/filter layer that can sit in front of old media and generate the segment metadata a future segmented renderer/display could consume.

## Important design rule

SSC does not synthesize motion. It does not speed up or slow down playback and does not create interpolated frames. The optional `--collapse-static` path preserves timestamps and uses variable frame duration.

## Requirements

- Python 3.10+
- NumPy
- FFmpeg + ffprobe

## Examples

Analyse an MP4 without modifying it:

```bash
python3 ssc_codec.py analyze movie.mp4
```

Analyse and create a high-efficiency H.265 MP4:

```bash
python3 ssc_codec.py encode movie.mp4 --profile efficient
```

Also collapse duplicate/near-duplicate frames into VFR holds:

```bash
python3 ssc_codec.py encode movie.mp4 --profile efficient --collapse-static
```

Maximum compression using AV1:

```bash
python3 ssc_codec.py encode movie.mp4 --profile max --collapse-static
```

Process an old MP3 and output bitrate-adaptive efficient Opus:

```bash
python3 ssc_codec.py encode song.mp3 --profile efficient
```

Keep MP3 output for compatibility:

```bash
python3 ssc_codec.py encode song.mp3 --profile compat
```

## Profiles

| Profile | MP4 video | MP3 input output | Goal |
|---|---|---|---|
| `compat` | H.264 | MP3 bitstream copy | broad compatibility / no MP3 generational loss |
| `efficient` | H.265/HEVC | Opus 128k | balanced efficiency |
| `max` | AV1 | Opus 96k | maximum compression / newer decoders |

## What the `.ssc.json` is for

A future renderer can consume the state map and choose, for example:

- `static` → retain the tile/pixel state and avoid needless work
- `low_motion` → adaptive low-power path
- `motion` → realtime path at source cadence
- `silence` → audio clock-gating candidate without shortening time

The manifest is deliberately separate from the media so it can be added to existing systems first, like a compatibility firewall.

## What this prototype can and cannot save

On a normal old monitor, SSC cannot stop the panel's own fixed refresh electronics. It can still reduce storage/network bitrate and provides metadata that a software compositor or future panel could use to avoid unnecessary rendering/decoding work. The largest display-power gains require hardware with panel self refresh, local memory, partial update, reflective/bistable pixels, or locally adaptive refresh.

## Next architecture step

The actual next-generation SSC bitstream would store **persistent spatial tiles + timestamped deltas + latency class + fidelity class**, rather than only encoding complete frames. That would allow a native player/display path to work on state changes directly.
