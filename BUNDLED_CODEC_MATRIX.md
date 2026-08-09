# Codec/runtime matrix

## Shipping policy

The current Linux packages bundle **no VLC, FFmpeg, LAME, libde265 or other
codec implementation**. They depend on distribution libVLC/FFmpeg. Therefore
there is no honest universal static list of “all codecs”. The contract is:

> MPCASU must pass an ordinary source/location to the installed libVLC runtime
> without rejecting it by filename extension. If that same runtime can play it
> directly but MPCASU cannot, the result is an MPCASU compatibility bug.

## Inspected development runtime

- libVLC/libvlccore/VLC base plugins: Ubuntu `3.0.23-1`.
- FFmpeg: Ubuntu `8.0.1-3ubuntu2`, shared build with the configuration captured
  in `THIRD_PARTY_COMPONENTS.md`/test logs.
- Native codec: CASUNAT2 revision 2, video key-state/tile and s16le PCM audio.
- Native rich subtitles: distribution libass ABI 9 renders preserved ASS/SSA
  documents to bounded transparent RGBA. Real PGS streams convert through
  FFmpeg's decoded subtitle-video boundary into typed, hashed, alpha-bounded
  RGBA regions. Authorized PGS/DVD/DVB/XSub source-deletion fixtures pass;
  broader malformed/language/platform coverage remains open.

## Current automated evidence

| Path | Covered behavior |
|---|---|
| STRICT source decode | RGB/YUV420/422/444, alpha, 8/10/12/16-bit, VFR, B-frames |
| CASUNAT2 converter | generated FFV1 video + PCM audio, exact source-deletion round trip, attached-cover normalization, real PGS region encoding |
| CASUNAT2 player | indexed native video reconstruction, exact PCM sink delivery, audio-only cover and timed PGS overlay presentation |
| libVLC adapter | generated exact-runtime demux/decode/track/clock matrix using bounded explicit dummy sinks |

The 2026-08-09 generated headless matrix isolates physical output from decode
by passing bounded `--aout=dummy --vout=dummy` options to the same in-process
backend. PCM/WAV, FLAC, MP3, Vorbis/Ogg, Opus and AAC/M4A all expose an audio
track and advance the clock. H.264/MP4, MPEG-4/MOV and MPEG-2/TS expose a video
track and advance the clock. HEVC/MKV, VP8/WebM, VP9/WebM, AV1/MKV and FFV1/MKV
advance to EOF but expose no decoded video track on this exact VLC 3.0.23 host,
so they are reported as five runtime `XFAIL`s rather than support. The Debian
player package depends explicitly on `vlc-plugin-base` and
`vlc-plugin-video-output`; physical audio/video output remains a separate host
matrix and stable release remains blocked until clean supported hosts pass it.

The release matrix still must add representative MP4/MKV/MOV/WebM/TS,
H.264/HEVC/VP8/VP9/AV1/MPEG-2, AAC/MP3/Opus/Vorbis/FLAC/PCM, subtitle formats,
network protocols, hardware decode and platform/device combinations against the
exact shipped runtime.
