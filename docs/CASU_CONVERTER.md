<!-- SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4 | SPDX-FileCopyrightText: 2026 Lino Casu -->
# CASU converter

The converter is deliberately a **sidecar conversion**, not a destructive
transcode. It decodes the selected MP4/MP3 stream with FFmpeg, records source
metadata and conservative temporal activity hints, and writes a UTF-8 JSON
manifest with the `.casu` extension.

```bash
casu convert input.mp4 --output input.casu
casu convert input.mp3 --output input.casu
casu benchmark input.mp4 --output benchmark.json

The benchmark report measures analysis time, source size, duration and segment
counts. Energy is reported as unavailable unless a real telemetry backend is
present; no savings are inferred from file size alone.
casu validate input.casu
casu validate --verify-source input.casu
casu play input.casu
```

`convert` accepts `--mode strict|visually_lossless|adaptive`; `strict` is the
default reference mode. The mode labels the analysis policy and does not make
an unverified pixel-identity or perceptual-quality claim. `--verify-source`
performs the structural validation and then checks the manifest's recorded
source path/fallback filename and SHA-256 digest.

The original media is never rewritten. The manifest records its absolute path,
filename, byte size and SHA-256 digest. Consumers must treat source timestamps
as canonical. If the source is moved, the player first tries the recorded path
and then the manifest directory plus the recorded filename; otherwise it fails
closed instead of playing an unrelated file.

`video.segments` and `audio.segments` carry explicit `start_s`, `end_s`,
`valid_until_s` and `deadline_s` timing fields, but remain scheduler hints only.
They do not
permit frame interpolation, retiming, pitch changes, dropped audio, hidden
colour changes or an assumption that a static hint is pixel-perfect. A missing,
stale or invalid manifest always falls back to ordinary legacy playback.

The current schema is `0.2` and identifies itself with the `MPCASU\\0` magic
field. This is a manifest identity marker; the media payload remains in its
original MP4/MP3 container for backward compatibility.
