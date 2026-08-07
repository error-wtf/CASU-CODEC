# CASU converter

The converter is deliberately a **sidecar conversion**, not a destructive
transcode. It decodes the selected MP4/MP3 stream with FFmpeg, records source
metadata and conservative temporal activity hints, and writes a UTF-8 JSON
manifest with the `.casu` extension.

```bash
casu convert input.mp4 --output input.casu
casu convert input.mp3 --output input.casu
casu validate input.casu
casu play input.casu
```

The original media is never rewritten. The manifest records its absolute path,
filename, byte size and SHA-256 digest. Consumers must treat source timestamps
as canonical. If the source is moved, the player first tries the recorded path
and then the manifest directory plus the recorded filename; otherwise it fails
closed instead of playing an unrelated file.

`video.segments` and `audio.segments` are scheduler hints only. They do not
permit frame interpolation, retiming, pitch changes, dropped audio, hidden
colour changes or an assumption that a static hint is pixel-perfect. A missing,
stale or invalid manifest always falls back to ordinary legacy playback.

The current schema is `0.2` and identifies itself with the `MPCASU\\0` magic
field. This is a manifest identity marker; the media payload remains in its
original MP4/MP3 container for backward compatibility.
