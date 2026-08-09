# Codec/runtime matrix

## Shipping policy

The current Linux packages bundle **no VLC, FFmpeg, LAME, libde265 or other
codec implementation**. They depend on distribution libVLC/FFmpeg. Therefore
there is no honest universal static list of “all codecs”. The contract is:

> MPCASU must pass an ordinary source/location to the installed libVLC runtime
> without rejecting it by filename extension. If that same runtime can play it
> directly but MPCASU cannot, the result is an MPCASU compatibility bug.

The same rule applies to URI schemes: non-empty, NUL-free locations reach
libVLC, whose installed access modules make the actual protocol decision.
Windows drive paths and `file:` URIs remain local-path inputs.

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
with bounded dummy audio and in-memory video callbacks on the same in-process
backend. PCM/WAV, FLAC, MP3, Vorbis/Ogg, Opus and AAC/M4A all expose an audio
track and advance the clock; external SRT, WebVTT and ASS tracks load against a
decoded Rawvideo/AVI base. A video codec passes only after libVLC writes a real
RV32 frame into the callback buffer. Rawvideo/AVI passes; H.264/MP4,
MPEG-4/MOV, MJPEG/AVI, HEVC/MKV, VP8/WebM, VP9/WebM, AV1/MKV, MPEG-2/TS and
FFV1/MKV deliver no frame in the privileged headless harness and are nine
runtime `XFAIL`s rather than support. The same H.264 callback probe delivered a
frame as the non-root desktop user, so runner identity is recorded as part of
the matrix and is not generalized into a release pass. The Debian
player package depends explicitly on `vlc-plugin-base` and
`vlc-plugin-video-output`; physical audio/video output remains a separate host
matrix and stable release remains blocked until clean supported hosts pass it.

A loopback HTTP server redirects to a generated WAV fixture. The runtime follows
the redirect, exposes the PCM track, advances its clock and seeks to one second.
A missing URL enters `ERROR`; VLC 3's zero-track/zero-time false EOF is normalized
to an opening failure. A separate generated HLS VOD playlist serves six seconds
of AAC-in-TS over loopback HTTP; libVLC exposes its track, advances playback and
seeks to three seconds. HTTPS, authentication, mutable live playlists,
discontinuities and hostile-network cases remain open.

A generated MP4 contains two AAC audio tracks and two embedded `mov_text`
subtitle tracks with German/English metadata. libVLC exposes both linked-list
description sets and accepts live selection of every concrete track identifier.
An AAC/MP4 chapter fixture exposes two chapters and accepts a real jump to
chapter index 1; the libVLC `set_title`/`set_chapter` ABI is bound as `void`.
A real four-second FLAC fixture accepts 1.5x playback, 125-millisecond audio
delay and pause/resume with the expected clock behavior. The dummy audio sink
accepts volume/mute writes but reports volume zero; this is transport-control
evidence, not a physical-output volume claim.
A generated five-fps Rawvideo/AVI fixture also proves paused single-frame
navigation by observing exactly one new, pixel-distinct RV32 callback. The
libVLC `next_frame` ABI is bound as `void`; no undefined return register is
interpreted as a success code.

The release matrix still must add representative MP4/MKV/MOV/WebM/TS,
H.264/HEVC/VP8/VP9/AV1/MPEG-2, AAC/MP3/Opus/Vorbis/FLAC/PCM, subtitle formats,
network protocols, hardware decode and platform/device combinations against the
exact shipped runtime.
