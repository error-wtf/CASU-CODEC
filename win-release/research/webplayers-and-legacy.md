# Web Player Tabs + Legacy browser paths (Windows decision)

Reference: `mpcasu_qt/webplayers.py`, `mpcasu_web/`, `web/` (native-smoke),
`web/README.md`.

## WebPlayerTabs (`mpcasu_qt/webplayers.py`)

- QtWebEngine embedded tabs for **Spotify / Hearthis / Tidal / Netflix /
  BROWSE** — official web players loaded in-process; persistent profile for
  logins (cookies stored under config dir). `_open_web_player` routes
  provider URLs here.
- **Legacy `play_video(url, title)`**: injects an HTML `<video>` element into
  a QWebEngineView to play a resolved googlevideo URL. This is an **obsolete
  browser-playback path** superseded by the frozen YouTube fix (loopback
  transport → libVLC). It must NOT be re-created in the Windows port.

**Decision (Windows):** Web-provider tabs (Spotify/Tidal/Hearthis/Netflix) are
a web-browser feature → **QtWebEngine optional**; for a self-contained native
port, either bundle Qt WebEngine (heavy) or open provider in the default
browser. This is a deliberate, documented choice; not silently dropped.
YouTube must never use QtWebEngine `<video>` — it uses the normal pipeline.

## mpcasu_web/ (legacy loopback launcher frontend)

- `mpcasu_web/index.html` + `player.js` — an older minimal web player.
- `web/README.md` references `mpcasu_web.py` which does **not exist** in the
  frozen tree (stale doc). Classification: **OBSOLETE/legacy**, superseded by
  `web_casu.py` + `web/`. Not part of the Windows release scope (documented,
  not silently ignored).

## web/native-smoke.html + native-smoke.js

- Browser **CASUNAT2 self-test**: loads a `.casu`, opens via `CasuNative`,
  selects tracks, reports frames/audio/subtitles/bitmaps/chapters/duration.
- Windows: a Wine browser can run this against the bundled web/pure or web/
  assets as a CASUNAT2 browser-decoder verification tool. Keep it in the
  bundled web assets (byte-identical), do not rewrite.

## Scope classification

| Item | Class | Windows action |
|------|-------|----------------|
| WebPlayerTabs (Spotify/Tidal/Hearthis/Netflix/Browse) | web feature | optional QtWebEngine OR external browser (documented) |
| WebPlayerTabs.play_video (HTML `<video>` for YouTube) | OBSOLETE | do NOT port |
| mpcasu_web/ + web/README (mpcasu_web.py) | OBSOLETE/legacy | excluded (documented) |
| web/native-smoke.* | dev verification | bundle in web assets, Wine browser run |
