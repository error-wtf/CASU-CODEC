<!-- SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4 | SPDX-FileCopyrightText: 2026 Lino Casu -->
# SSC temporal-state sidecar format v0.1

## Purpose

SSC v0.1 is a compatibility layer for legacy media. The media remains a normal MP4/MP3-compatible stream while a sidecar describes temporal state so a future compositor, decoder, or segmented display scheduler can avoid redundant work.

## Fundamental unit

The fundamental scheduling unit is not a global frame. It is a **state interval**:

```text
segment = {start_s, end_s, duration_s, state}
```

Video states in v0.1:

- `static`
- `low_motion`
- `motion`

Audio states in v0.1:

- `silence`
- `low_level`
- `active`

The state is a hint only. It must never alter source timestamps by itself.

## Native v0.2 direction

A future native bitstream should add spatial tiles and explicit integrity constraints:

```text
TileState {
  tile_id
  x, y, width, height
  valid_from
  valid_until
  base_state_hash
  delta_payload
  temporal_class
  max_latency
  fidelity_class
  color_state
}
```

Suggested temporal classes:

- `HOLD` — state persists until changed
- `ADAPTIVE` — update cadence may be reduced without changing event timing
- `REALTIME` — preserve source cadence and latency
- `LOSSLESS_REALTIME` — no temporal simplification permitted

Suggested invariant:

```text
presented_information(t) == source_information(t)
```

for all fidelity-critical events. Optimisation is permitted only on redundant representation, not by inventing or time-warping content.
