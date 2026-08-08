<!-- SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4 | SPDX-FileCopyrightText: 2026 Lino Casu -->
# CASU format definition

## Name and scope

**CASU** means **Codec for All Segmented Units**.

- Codec/container: `CASU`
- File extension: `.casu`
- Future player: `MPCASU`

MPCASU is an application built to play CASU and legacy media such as MP4,
MP3, MKV and other formats through established decoders. It is not the name
of the codec itself.

## Core unit

CASU does not treat every complete frame as the only meaningful unit. Its
compatibility sidecar records the information needed to reason about a
segment's state over time:

\[
\boxed{\text{State}+\text{Segment}+\text{Change}+\text{Timing}}
\]

The legacy frame stream remains the source of truth. CASU adds state/change
metadata; it does not invent frames, reorder timestamps or silently alter the
audio/video signal.

## Compatibility rule

An ordinary file remains playable without a `.casu` sidecar. A CASU-aware
consumer may use the sidecar to avoid redundant analysis, compositing or
transfer work. If the sidecar is missing, stale or ambiguous, the consumer
must fall back to full-fidelity legacy playback.

## State interval

```text
segment = {
  start_s,
  end_s,
  duration_s,
  state,
  source_timing
}
```

Video states currently include `static`, `low_motion` and `motion`; audio
states include `silence`, `low_level` and `active`. These are scheduler hints,
not permission to shorten the source timeline.

