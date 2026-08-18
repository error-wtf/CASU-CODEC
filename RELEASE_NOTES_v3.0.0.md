# CASU / MPCASU 3.0.0 — Linux Release Notes

**Release:** `v3.0.0` — "Playlist Everywhere"
**Date:** 2026-08-18
**Repository:** [error-wtf/CASU-CODEC](https://github.com/error-wtf/CASU-CODEC)

## What's new

### Native, format-aware playlist support in every player

3.0.0 fixes the biggest usability gap of the 2.0 release: **local-file
playlists are now recognised, resolved and played back immediately**. In 2.0,
plain M3U files (without an `#EXTM3U` header) and several common playlist
formats were rejected as `unknown playlist format`, and entries could not be
matched back to media files.

All three players now natively understand these playlist formats:

- **M3U / M3U8** (plain and Extended, with `#EXTINF` titles)
- **PLS**
- **WPL** (Windows Media Player)
- **XSPF**
- **JSPF** (JSON XSPF)
- **ASX / WMX / WVX** (Windows Media, case-insensitive tags/attributes)
- **RMP / RAM** (RealMedia, XML Smil and plain-line variants)
- **MPCASU JSON** (the player's own session format)

Local paths are resolved relative to the playlist directory, `file://` and
URL-encoded (`%20`) paths are decoded, and entries that point to media dropped
together with the playlist are matched by name — so loading an M3U alongside
its audio files just works. Stream URLs (HTTP/S, RTSP, RTMP, etc.) are kept
verbatim and play through the normal stream path, exactly as before.

### Where

- **`mpcasu`** — Qt desktop player: expanded Playlist dialog + playlist tree,
  relative/URL-encoded resolution, XSPF export, per-entry titles,
  Shift/Ctrl multi-select editing, format-aware save dialog, hang-free
  in-process file dialogs, and a throttled visualizer (no more CPU-freeze).
- **`web-casu`** — local web player: same native format detection, path
  resolution and name matching in the browser front end.
- **Pure Web Release** — static web player: identical playlist engine.
- **`casu-codec`** — shared `casu.playlist` module drives them all.

## Stability & UX fixes (3.0.0)

- **No more hang/freeze:** the Qt visualizer's 60 Hz repaint loop ran even
  while hidden (e.g. during video playback), pegging the CPU and freezing the
  UI. It now skips all work while not visible and caches the background, so
  the player stays responsive.
- **No more double-load:** choosing a playlist together with the media files
  it references now adds each file once (they are covered by the playlist
  group) instead of appearing both as playlist children and as separate rows.
- **Playlist plays from track 1:** selecting a playlist and pressing Play now
  starts at its **first track**, and after a track ends the player advances to
  the **next track inside the same playlist** (Next / Previous step through its
  children) instead of jumping within the queue or getting stuck.
- **Hang-free "Choose files":** the file dialog is now the in-process Qt
  dialog instead of the native/portal one, which was a common freeze source on
  Wayland (and some X11) sessions.
- **Multi-select editing:** select many queue rows with Shift/Ctrl and remove
  or play them together (context menu and Delete key).
- **Better save playlist:** the save dialog now adds the correct extension
  automatically for the chosen format (M3U/PLS/XSPF/JSON).
- **Wayland **and** X11:** the launcher now detects the session and picks the
  platform (xcb when an X11/XWayland `DISPLAY` exists, otherwise wayland)
  instead of forcing one, so the player runs on both without hanging.

## Packages

| File | Contents |
|---|---|
| `casu-codec_3.0.0_all.deb` | CLI, codec, shared playlist engine, web assets |
| `casu-converter_3.0.0_all.deb` | Graphical converter |
| `mpcasu_3.0.0_all.deb` | Qt desktop player |
| `web-casu_3.0.0_all.deb` | Local web player |
| `MPCASU-PURE-WEB-3.0.0.zip` | Static Pure Web player |

## Install

```bash
sudo dpkg -i casu-codec_3.0.0_all.deb casu-converter_3.0.0_all.deb \
             mpcasu_3.0.0_all.deb web-casu_3.0.0_all.deb
sudo apt-get -f install
```

See the [README](README.md) for full usage and requirements.

## Testing

- Full suite: **409 passed, 14 skipped** (was 398 in 2.0.0).
- 11 new playlist tests covering plain M3U, relative/URL-encoded paths, PLS,
  XSPF, WPL, ASX (case-insensitive), JSPF, RMP/RAM, `file://` URLs and
  malformed-XML rejection.
- 13 browser-engine playlist tests pass for both the Pure Web and `web-casu`
  front ends (M3U, PLS, XSPF, WPL, ASX, JSPF, RMP/RAM, URL-encoded and
  `file://` matching).

**License:** Anti-Capitalist License 1.4 / All Rights Reserved, Lino Casu.
