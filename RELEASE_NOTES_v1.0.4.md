# Release Notes — CASU/MPCASU 1.0.4

UX-parity release: the Qt desktop player now follows the web player's
interaction model (review-driven), spotDL is the Spotify provider in both
players, and the release metadata/wording is consistent.

## Qt desktop player (mpcasu)

* Transport decluttered: main row = Previous · Play · Next · Volume ·
  Fullscreen; second row = Shuffle · Repeat · Speed · Visualizer · ⋯;
  everything advanced (Stop, ±10 s, A–B, Snapshot, Record, tracks, output,
  chapters, sync, subtitle load, frame step, info) lives in the ⋯ panel.
  The duplicate fullscreen button is gone.
* Fullscreen is now video fullscreen: sidebar/playlist/topbar/transport/
  diagnostics/status bar hide on entry; a minimal overlay transport appears on
  mouse move and auto-hides after 2.5 s; Esc and double-click toggle.
* Responsive: below 1200 px the sidebar collapses to an icon rail; below
  1000 px the playlist panel auto-hides; topbar gains ☰ (nav) and ☷ (queue)
  toggles; the video stage always keeps priority.
* Drag & drop with red "DROP TO PLAY / ADD TO QUEUE" overlay; files,
  playlists, CASU/MP5 containers and stream URLs accepted.
* Queue product maturity: view filter (All/Files/Streams/Playlists/CASU/
  YouTube/Spotify) like the web views, recursive queue search incl. playlist
  children, persistent rename (display titles), real video thumbnails loaded
  asynchronously behind the glyph placeholder.
* Empty state hero like the web (icon + "Drop media here"), caption shows the
  playlist/EXTINF stream name while playing, LIVE GUIDE diagnostics card
  shows now/next from a loaded EPG.
* Options page gains Providers status (libVLC/FFmpeg/yt-dlp/spotDL/Deno) and
  recording options: storage folder, split-by-time, container format.
* Recording: one-click with per-part rotation when splitting is enabled.
* Startup geometry clamped to the screen and centered (no more off-screen
  panels or shifted click regions after fullscreen cycles).

## Spotify (both players)

* Spotify search uses spotDL (`spotdl save`, metadata only); results carry
  real Spotify URLs and are labelled SPOTIFY.
* Spotify playback resolves via `spotdl url` (Spotify metadata → YouTube
  match); without spotDL or on blocked networks the players say so honestly
  and offer the explicit "Find on YouTube" handoff (oEmbed title).
* `/show/` and `/artist/` URLs are recognised.
* Legal/consent texts corrected: YouTube = yt-dlp, Spotify = spotDL.

## Verification (installed 1.0.4)

* `pytest -m 'not media'`: 225 passed (incl. release-consistency and
  provider regression tests).
* `tools/acceptance_qt.py` (Xvfb, installed binary): window, MP4/MP3/
  CASUNAT2/CASUNAT1*/MP5 playback, pause/seek, fullscreen enter/exit,
  visualizer, playlist default expansion + children, choose-files open/
  reopen, internet stream, Escape, resize (*CASUNAT1 start is slow under
  Xvfb load; verified OK in dedicated runs).
* `tools/acceptance_web.py`: 16/16.

## Remaining limitations

* Gates 4–6 stay PARTIAL (historical Tk matrices not fully re-run on Qt).
* This host: api.spotify.com/open.spotify.com blocked (410/404) → Spotify
  network flows fail honestly here; they work where Spotify is reachable.
* spotDL is optional (venv /opt/casu-spotdl); the DEB does not hard-depend
  on it — Options → Providers shows the install command.
