# Source and research provenance

## Product source

- Repository: `/home/error/Lino-Codec`
- Recorded baseline HEAD: `d9c83ee`
- Implementation license: repository `LICENSE`
- Supplied specifications and gates: `docs/references/` plus the externally
  supplied recovery files listed in the user request.
- Supplied visual assets: the inspected CASU/MPCASU red/black logo, icon and UI
  mockup images; packaged assets remain in `assets/`.

## Primary implementation references

| Upstream | Use | Copy status |
|---|---|---|
| https://github.com/videolan/vlc | libVLC embedding, runtime capability and event/API research | no source copied |
| https://www.videolan.org/vlc/download-sources.html | stable-source/version research | no source copied |
| https://ffmpeg.org/ and https://ffmpeg.org/ffmpeg.html | timestamp/decode/probe behavior | no source copied |
| https://ffmpeg.org/pipermail/ffmpeg-devel/2021-December/288884.html | FFmpeg graphics-subtitle/sub2video behavior used for the PGS decoding boundary | no source copied |
| https://videolan.videolan.me/vlc/master/group__libvlc__media__player.html | public libVLC API contract | no source copied |
| https://github.com/libass/libass and its public `libass/ass.h` | stable ASS image-list/rendering ABI and lifecycle | no source copied; dynamically uses distribution `libass9` |

## Architectural/UX research only

| Upstream | Boundary |
|---|---|
| https://gstreamer.freedesktop.org/documentation/ | clocks/events/plugin architecture only; not a playback backend |
| https://mpv.io/manual/stable/ | application/client/render separation only; not a playback backend |
| https://github.com/error-wtf/webamp-embed | playlist/audio UX reference; no browser wrapper or copied code |
| https://github.com/lameproject/lame | MP3 encoding/licensing research; not used for playback |
| https://github.com/strukturag/libde265 | decoder/tile/WPP API research; not linked |
| https://github.com/ggrandes-clones/mp3_codec | historical/educational only; provenance not sufficient for production |
| https://www.libhunt.com/topic/mp4 | discovery index only; never authoritative evidence |

No research-only project has been vendored or modified. If that changes, this
file must record an exact revision, purpose, patch set and license location.

The PGS, DVD, DVB and XSub acceptance fixtures are read directly from VideoLAN's
public stream test collection during authorized local testing. They are not
copied into the repository or release artifacts:

- `https://streams.videolan.org/samples/sub/PGS/`
- `https://streams.videolan.org/samples/sub/DVD-short/`
- `https://streams.videolan.org/samples/sub/dvbsub/`
- `https://streams.videolan.org/samples/sub/divx_xsub/`
