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

## Native revision 2

CASUNAT2 is the standalone codec/container revision. It stores bounded stream
descriptors, complete canonical video key states, hash-linked tile updates,
timestamped canonical PCM audio, writer-declared recovery points, a real
byte-offset seek index, bounded hashed attachments, an integrity table and a
mandatory END chunk. Attached-picture streams are attachments with the semantic
role `cover-art`; they are never video timelines.
Bitmap subtitles use typed `SUBTITLE_BITMAP` chunks containing timed, bounded,
hashed RGBA regions and explicit canvas coordinates. They remain selectable
subtitle tracks and are not burned into CASU video states.

CASUNAT2 never relies on a stored source path. A conforming reader rejects
unknown versions/types, invalid lengths/offsets, mismatched tile dependencies,
decoded output beyond configured limits and a failed integrity digest. The
exact binary contract and current release boundary are summarized in the
repository-root `CASU_FORMAT_SPECIFICATION.md`.

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
