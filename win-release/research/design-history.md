# Design History (git log read-only analysis)

Key turning points that shaped the current architecture — the Windows port
must not re-introduce the solved bugs.

## YouTube playback (most volatile area)

- `7480fe4` libVLC direct stream for YouTube.
- `b8810e1` automatic yt-dlp fallback on VLC 3.x extract/TLS failure.
- `97ddc0b / 353a4bd / 19aa079` web-casu style: yt-dlp resolve → browser
  `<video>` in NOW PLAYING (QtWebEngine) + h264/itag-18 force.
- `8fc6418 / 2462138 / 86b7896` local yt-dlp HTTP streamer, then
  `player_client=android` primary + android_vr/ios cycle + **browser
  fallback** — the symptom-patching spiral.
- `470b5a5` (current, frozen): **one shared resolver**
  (`casu.locations.resolve_media_location`, same as web-casu), thin loopback
  byte/range transport (no HTML/player_client), `LibVLCBackend.open_source`,
  lifecycle fix: stop OLD session before starting the NEW proxy (the
  “Playback error detected” root cause). No browser, no second player.

**Lessons:** Resolver ≠ player. Transport ≠ player. Never destroy the
transport after starting it for the source about to open. Don’t rotate
player clients to fix 403s; use the resolver web-casu already proves.

## Player / overlays

- Flicker fix: libVLC owns the native VideoSurface exclusively; caption/
  badge/empty-hint overlays hidden in video mode; `NOW PLAYING` is a fixed
  heading with a separate dynamic title label.

## Pure web player

- Backend-free build: YouTube IFrame API + oEmbed titles, bundled hls.js,
  client-side CASU, PHP helpers optional, playlist preloaded + collapsible.
- Fixed bugs during development: `Number(null)=0` volume mute, WP overlay
  click-blocking (particles + exit gate), CDN cache-staleness (version
  queries), responsive embed layout.

## Freeze (current)

- `36df249` freeze as final v2.0.0 Linux release.
- `7e56632` baseline + win-release analysis start; Pure Web 2.0.0 published.

## For the port

- Keep: single-player architecture, shared resolver, transport-only proxy,
  lifecycle ordering, native-surface ownership, fixed NOW PLAYING heading,
  shared design tokens, integrity-first CASU formats.
- Do NOT rebuild: the android/android_vr/ios roulette, browser fallbacks,
  per-tool duplicated codec logic.
