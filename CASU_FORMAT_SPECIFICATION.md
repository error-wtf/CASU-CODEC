<!-- SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4 | SPDX-FileCopyrightText: 2026 Lino Casu -->
# CASU 1.0 format specification status

CASU means **Codec for All Segmented Units** and uses the `.casu` extension.

## Current 1.0 compatibility format

The released CASU 1.0 implementation is a validated, deterministic JSON
sidecar. The original media file remains the source of truth and is never
modified by conversion. A sidecar contains:

```text
format.magic                 MPCASU\0
casu.name                    CASU
casu.container_extension     .casu
casu.analysis_mode           strict | visually_lossless | adaptive
source                       filename, duration, size, optional SHA-256
streams                      probed source stream metadata
video.segments               timestamped state hints
audio.segments               timestamped state hints
integrity                    source timing and validation policy
```

This is intentionally not described as a native compressed elementary-stream
container yet. It is a legacy-compatible state/provenance layer. Missing,
stale or ambiguous sidecars must fall back to full-fidelity legacy playback.

## Timing and state rules

`start_s`, `end_s` and `duration_s` are finite, non-negative seconds. Segments
must be ordered and non-overlapping. The source timeline is authoritative:
`HOLD` or `static` is a scheduler hint and never removes duration, samples or
frames. Audio silence is also time and must not be collapsed.

## Integrity and recovery boundary

The current sidecar verifies manifest structure and, when a source hash and
size are recorded, verifies the immutable source before CASU playback. The
current release does not yet claim native segment/index/footer checksums,
cryptographic signatures, in-file recovery key states, attachments, or
compressed media payloads. Those are reserved for a versioned native CASU
container and must not be inferred from this JSON sidecar.

## Version policy

Readers must reject an unknown `format.magic`, invalid version fields, unsafe
numeric values, overlapping intervals and manifests exceeding the validator's
segment safety limit. Newer native formats require an explicit reader version;
they must never be silently interpreted as an older sidecar.

The detailed compatibility definition is maintained in
[`docs/CASU_FORMAT_SPEC.md`](docs/CASU_FORMAT_SPEC.md). The CLI provides:

```text
casu analyze input.mp4
casu convert input.mp4 -o output.casu
casu verify output.casu
    casu info output.casu
    casu benchmark input.mp4 -o report.json
```

`benchmark` reports measured analysis time, source duration, segment counts
and input size. It deliberately reports energy as unavailable unless a future
platform telemetry backend supplies a real measurement.
