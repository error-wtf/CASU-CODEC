# WEB CASU Player — Pure Web build

A backend-free, exact-feel copy of the WEB CASU Player that runs on **any
static web server** (plain FTP upload, GitHub Pages, nginx, Apache, …).

## Why

The reference player (`web_casu.py` in the frozen repo) uses a Python/yt-dlp
backend for YouTube resolution/search, transcoding and stream proxying. The
`error.wtf` web server only offers FTP access and its PHP runtime has
`exec`/`shell_exec`/`system` disabled and no Python/yt-dlp/ffmpeg installed —
so the Python backend cannot run there.

This build keeps every feature that the browser itself can provide and
replaces the backend-dependent ones with pure-web equivalents.

## Features (pure web, no backend)

- Local files: drag & drop / file picker, ID3v2 tags + cover art, subtitles
  (SRT/VTT) matched by name, object-URL playback
- Playlists: M3U / Extended M3U / PLS, group headers, tvg-id/group/logo
  attributes, save current queue as M3U
- IPTV / EPG: client-side XMLTV parsing, “NOW / NEXT / UPCOMING” guide
- Direct streams & radio: play any HTTP(S) audio/video URL; HLS (`.m3u8`)
  through the bundled `hls.js`
- YouTube: plays any YouTube link (video, Shorts, playlists, live) through
  the YouTube **IFrame Player API** — no API key, no backend; titles and
  thumbnails come from YouTube’s oEmbed endpoint
- CASU: `CASUNAT1` / `CASUNAT2` / sidecar files verified and played in the
  browser (`casu-native.js`)
- Visualizer: WebAudio spectrum for local, same-origin and relayed audio
- Transport: play/pause, seek, volume, mute, speed, shuffle, repeat (off/all/
  one), A–B loop, snapshot, PiP, fullscreen, keyboard shortcuts
- Queue persistence: network/YouTube items are restored from `localStorage`
  (object-URL local files cannot survive a reload)

## Optional server extras (not required)

The player probes `php/ping.php` at startup. If it answers, it additionally
uses:

| file | purpose |
|---|---|
| `php/stream.php` | same-origin relay for allow-listed radio streams (enables the visualizer + bypasses hotlink blocks) |
| `php/catalog.php` | server-side fetch of remote M3U/XMLTV URLs that send no CORS headers |
| `config.js` → `endpoints.search` | a resolver endpoint if you ever host yt-dlp (enables YouTube search + direct googlevideo playback) |

Point `config.js` endpoints elsewhere or to `null` to tune behaviour; on a
pure static host the player just runs without them.

## Files

```
index.html      player UI
app.js          pure-web player logic
styles.css      red/black web-casu look
config.js       endpoint configuration
casu-native.js  client-side CASUNAT1/CASUNAT2 decoder
libs/hls.min.js bundled hls.js (HLS for non-Safari)
php/            optional server helpers (ping/stream/catalog)
assets/         icons
```

## Deploy

Upload the whole directory via FTP. No build step, no Python, no composer.

Local preview:

```sh
python3 -m http.server 8080 --directory pure-web-release
# open http://127.0.0.1:8080/
```

YouTube playback needs a real `https` or `http` origin (the IFrame Player API
requires an `origin` parameter) — it works over `http://127.0.0.1`.
