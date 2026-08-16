# VLC + Webamp Reference Mechanics (Windows port)

## VLC (`/home/error/vlc`) — playback mechanics reference

libVLC already provides: access (incl. HTTP/Range/seek), demux, decode,
audio/video output, track handling, subtitles, chapters, rate, snapshot,
events (Opening/Buffering/Playing/Paused/Stopped/EndReached/EncounteredError),
media states (6=Ended, 7=Error), error diagnostics.

Confirmed API (from `include/vlc/libvlc_media_player.h`,
`libvlc_media.h`):
- `libvlc_media_player_set_hwnd(player, void* drawable)` → Windows HWND.
- `libvlc_media_new_location(instance, mrl)` → HTTP/media URL.
- (X11 sibling `set_xwindow` — Linux only, do not port.)

**MPCASU must NOT duplicate VLC's work.** MPCASU owns: UI, controller state
machine, source resolution, YouTube transport, playlists/library/EPG/settings,
stage detection, overlay policy. libVLC owns everything inside the media
pipeline. Windows port: bundle `libvlc.dll` + `plugins/` (the VLC modules tree
`access, access_output, audio_filter, audio_mixer, codec, demux, ...` must be
present and discoverable — libvlc.dll alone is insufficient).

## Webamp (`/home/error/webamp-embed`) — style / interaction reference

- Local files via drag-drop/file picker with password gate (its own choice).
- M3U playlist parser; streams loaded **directly** (browser plays them) with an
  optional relay (`stream.php?id=`) mapping each station to a relay id (the
  PHP relay + 122 s reconnect logic mirror the approach the pure-web player
  also uses). Webamp options: `initialTracks`, `initialSkin` (skinnable).
- Playlist + transport + visualizer = classic Winamp idiom (red/black family).

**What to borrow for MPCASU Windows:** the playlist/transport/visualizer
interaction idiom and the red/black family (already mirrored via
`casu/design.py` tokens). **Not to copy:** password-gating local files,
server-dependent relay.

## Provenance summary

| Concept | Origin | Windows port |
|---------|--------|--------------|
| Playback pipeline + timing | libVLC | use libVLC C API (HWND) |
| HTTP/Range/seek | libVLC access | use libVLC, don't reimplement |
| Transport bar / controls | VLC-ish + Webamp | Qt transport bar |
| Playlist pane + thumbs + skin | Webamp/Winamp | Qt playlist model |
| Red/black branding, tokens | MPCASU design (web-first) | shared design constants |
| YouTube via normal pipeline | MPCASU fix (shared resolver) | transport → libVLC |
