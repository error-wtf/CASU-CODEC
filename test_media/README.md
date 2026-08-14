<!-- SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4 | SPDX-FileCopyrightText: 2026 Lino Casu -->
# Casu reference test media

The local test asset is downloaded from the owner's YouTube publication:

- Title: `Lino.Lol - TEST PATTERN`
- URL: https://www.youtube.com/watch?v=JG4fMJXvpZ0
- YouTube ID: `JG4fMJXvpZ0`
- Download format: YouTube format `18` (H.264/AAC MP4, 640×360, 25 fps)
- Duration: `1056.461497` seconds
- SHA-256: `e8d757b6f088bb719976e910e6ebe1fa907ebfcfaacb1bf4337bd71095285a72`

The media file is included as an owner-authorized reference fixture. Download
it again with the command below if a clean checkout needs to reproduce it:

```bash
yt-dlp -f 18 --merge-output-format mp4 \
  -o 'test_media/lino_lol_test_pattern.%(ext)s' \
  'https://www.youtube.com/watch?v=JG4fMJXvpZ0'
```

Override the test asset with `CASU_TEST_VIDEO=/path/to/file.mp4`.

## Audio reference

The MP3 fixture is copied from `/home/error/Musik/Lino Casu - ERROR.mp3`:

- Local fixture: `lino_casu_error.mp3`
- Codec: MP3, 48 kHz, stereo, approximately 183.752 kb/s
- Duration: `276.639979` seconds
- SHA-256: `21881d98108bf9038d8f9bb539cf94047e00dc0f2b28cf5d7849ce16886a99b4`
- The file contains an embedded PNG cover-art stream; CASU analyses the MP3
  audio stream and preserves the source metadata boundary.

Override it with `CASU_TEST_AUDIO=/path/to/file.mp3`.

## Additional owner-provided fixtures

- `giancarlo.mp4` with the generated `giancarlo.mp4.casu` sidecar
- `lino_casu_error_original.mp3`, the original audio supplied for playback tests

The sidecar is optional metadata. The original MP4/MP3 remains the canonical
source and remains usable by ordinary media players.

## Regenerated conversion demo fixtures (1.0.0)

Generated from a deterministic 6-second `testsrc`/sine clip (320×240, 12 fps,
H.264/AAC) so every artifact is reproducible without external downloads:

- `demo_clip.mp4` — the source clip
- `demo_casunat2.casu` — CASUNAT2 segmented container produced by
  `casu pack-v2` (2 streams, video key states + tile updates + PCM audio,
  integrity verified)
- `demo.mp5` — CASU MP5 container produced by `casu pack-mp5` (strict mode,
  original source embedded and SHA-256 bound)
- `demo_clip.mp4.casu` — CASUNAT1 compatibility envelope produced by
  `casu pack` (payload SHA-256 verified)

Reproduce them with:

```bash
ffmpeg -y -f lavfi -i "testsrc=duration=6:size=320x240:rate=12" \
  -f lavfi -i "sine=frequency=440:duration=6" \
  -c:v libx264 -preset ultrafast -c:a aac -shortest test_media/demo_clip.mp4
casu pack-v2 test_media/demo_clip.mp4 -o test_media/demo_casunat2.casu
casu pack-mp5 test_media/demo_clip.mp4 -o test_media/demo.mp5
casu pack test_media/demo_clip.mp4 -o test_media/demo_clip.mp4.casu
```

`lino_casu_error.casu` and `lino_lol_test_pattern.casu` are intentionally
invalid sidecars kept as fail-closed rejection fixtures; the player refuses
them by design. Do not regenerate them into valid containers.
