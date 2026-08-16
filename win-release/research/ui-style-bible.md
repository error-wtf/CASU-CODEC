# UI Style Bible + Provenance

Single design source: `casu/design.py` tokens are mirrored verbatim by
`mpcasu_qt/theme.py`, the web players (`web/styles.css :root`), and the
converter. **One product family, one look.**

## Palette (identical everywhere)

| Token | Value | Use |
|-------|-------|-----|
| --bg | #07090b | window background |
| sidebar | #0c0f12 | sidebar / queue panel |
| panel | #101317 | cards, transport |
| panel2 | #15191e | search input bg |
| line | #252a30 | borders |
| badge border | #383d43 | strong borders |
| stage | #050608 | video stage |
| --red | #ff1e2d | accent, active, play |
| red_dark | #3a1015 | hover/active wash |
| red_glow | #ff1e2d55 | glow |
| --text | #f4f5f7 | primary text |
| secondary | #b9bec5 | nav text |
| muted | #858b93 | faint text |
| ok/warn/error | #25c065/#e0a010/#ff4040 | status |
| toast | #171b20 / border #444 | toasts |

## Metrics (identical)

sidebar 240, playlist/right panel 310, topbar 72, transport 66, radius
shell 18 / panel 10 / control 7, control height 38, transport button 40,
play button 52, thumbnail 54×38, paddings 12/8/18.

## Layout (MPCASU desktop, from main_window.py)

```
[ Sidebar 240 ] [ Workspace ] [ Playlist 310 ]
   nav groups      topbar (NOW PLAYING + search + ☷)
                  stage (video surface / cover / visualizer)
                  seek slider
                  transport bar (transport buttons)
                  cards (segmented / integrity / EPG)
```

- **NOW PLAYING** is a fixed heading; the dynamic media title lives in a
  separate label, never replacing the heading and never over the native
  surface.
- Sidebar rail mode at narrow width (<1200 → 70px icons); queue auto-hides
  at <1000 and becomes a drawer via ☷.
- Transport: shuffle, prev, play, next, repeat, A–B, snapshot, speed, mute,
  volume, viz, PiP, fullscreen, track/chapter selects.

## Provenance

- Transport bar + play/pause/seek/volume/repeat/shuffle: classic player
  idiom (VLC-like mechanics; libVLC provides the timing).
- Playlist pane + thumbnails + queue grouping: Webamp/Winamp-inspired
  (drag, double-click, tools ✎/×, group headers).
- Dark/red branding, status/cards/diagnostics: MPCASU original design
  (web-first, mirrored into Qt via shared tokens).
- The WP page embeds Webamp (webamp-embed) next to the pure-web player —
  same red/black family, deliberately.

## Port rules

- Qt must reproduce the same layout, metrics, colors, hover/pressed/active
  states, toasts and dialogs (Qt stylesheets fed from the same constants).
- Not a redesign. UI screenshot gates: Linux reference vs Wine.
- DPI 100/125/150/200% must not break metrics (use logical pixels + Qt
  scaling; native video window untouched by scaling).
