# Casu reference test media

The local test asset is downloaded from the owner's YouTube publication:

- Title: `Lino.Lol - TEST PATTERN`
- URL: https://www.youtube.com/watch?v=JG4fMJXvpZ0
- YouTube ID: `JG4fMJXvpZ0`
- Download format: YouTube format `18` (H.264/AAC MP4, 640×360, 25 fps)
- Duration: `1056.461497` seconds
- SHA-256: `e8d757b6f088bb719976e910e6ebe1fa907ebfcfaacb1bf4337bd71095285a72`

The media file is intentionally ignored by Git because it is a reproducible
test fixture, not source code. Download it again with:

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
