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
  RGBA regions; DVD/DVB/XSub fixtures remain open.

## Current automated evidence

| Path | Covered behavior |
|---|---|
| STRICT source decode | RGB/YUV420/422/444, alpha, 8/10/12/16-bit, VFR, B-frames |
| CASUNAT2 converter | generated FFV1 video + PCM audio, exact source-deletion round trip, attached-cover normalization, real PGS region encoding |
| CASUNAT2 player | indexed native video reconstruction, exact PCM sink delivery, audio-only cover and timed PGS overlay presentation |
| libVLC adapter | source/protocol acceptance contract, in-process play/state/track APIs |

An additional 2026-08-09 headless development-runtime smoke reached active
in-process playback and advancing timestamps for the bundled MP4, but that
specific installed VLC 3.0.23 runtime logged that its H.264 decoder module was
unavailable and the sandbox had no PulseAudio/ALSA output. This is an
environment/runtime matrix failure, not something MPCASU may conceal. The
Debian player package therefore depends explicitly on `vlc-plugin-base` and
`vlc-plugin-video-output`, and stable release remains blocked until decoding
and real audio output pass on clean supported hosts.

The release matrix still must add representative MP4/MKV/MOV/WebM/TS,
H.264/HEVC/VP8/VP9/AV1/MPEG-2, AAC/MP3/Opus/Vorbis/FLAC/PCM, subtitle formats,
network protocols, hardware decode and platform/device combinations against the
exact shipped runtime.
