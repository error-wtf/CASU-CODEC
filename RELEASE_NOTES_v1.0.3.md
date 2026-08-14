# Release Notes — CASU/MPCASU 1.0.3

Product stabilization pass over 1.0.2: real user workflows reproduced,
fixed and re-verified against the installed packages.

## CASU format routing (sidecar confusion removed)

* Routing is magic-byte first: CASUNAT2 → native standalone playback,
  CASUNAT1 → compatibility container (verified extraction), MP5 → enhanced
  container (verified extraction), normal media → libVLC, legacy JSON CASU
  manifest → explicitly labelled legacy compatibility path with a clear
  re-pack hint on validation failure.
* Misleading primary UI wording ("CASU sidecar found", "Legacy + CASU
  sidecar", "CASU sidecar + libVLC") replaced with accurate terminology.
* New mandatory standalone test `tests/test_standalone_casu.py`: a CASUNAT2
  file copied alone into a clean directory still verifies, inspects, opens,
  plays video+audio and seeks.

## Spotify — fake implementation removed

* `casu/spotify.py` is now a metadata-only provider (public oEmbed lookup)
  with an explicit "Find on YouTube" handoff. No Spotify URL reaches yt-dlp,
  no YouTube result is labelled Spotify.
* `resolve_media_location()` refuses Spotify URLs with an honest notice.
* Qt Spotify view: URL → metadata → "FIND ON YOUTUBE" entry → explicit
  handoff search; Web search dialog does the same via
  `/api/spotify-metadata`.
* Regression tests: `tests/test_providers.py`.

## Qt desktop player

* Transport parity with the web player (shuffle/prev/PLAY/next/repeat, A–B
  loop, snapshot, record, speed, mute, volume, visualizer toggle,
  fullscreen), web tokens throughout.
* Playlists: newly added playlists expanded by default, double-click
  toggles the group instead of playing the .m3u, expansion state survives
  rerenders (collapsed-set tracking).
* Fullscreen uses the real window state (no stale boolean); Escape
  state machine: in-window page → fullscreen → nothing destructive.
* Visualizer: real measured spectrum/waveform for audio-only media (bridge
  fix, attached-pic streams no longer disable it).
* Options page gains a configurable recordings/snapshots folder; recording
  works one-click into that folder.
* MP5 files now route through the extraction backend (were sent raw to
  libVLC and failed); MP5 extraction uses a per-user temp dir (root-owned
  /tmp/mpcasu-mp5 permission bug).

## Web player

* Choose files / Add URL live in the playlist panel; real-toggle fullscreen
  with `fullscreenchange` sync; explicit dialog cancel handlers; versioned
  asset URLs + `/api/version` auto-reload guard against stale caches.

## Verification (installed 1.0.3 packages)

* `tools/acceptance_qt.py` on Xvfb: 16/16 workflow checks OK (playback of
  MP4/MP3/CASUNAT2/CASUNAT1/MP5, pause/seek, fullscreen enter/exit,
  visualizer, playlist default expansion, choose-files open/reopen,
  internet stream, Escape, resize) + offscreen run 11/12 (CASUNAT1 start is
  slow headless-offscreen; verified OK on Xvfb).
* `tools/acceptance_web.py` (Chromium): 16/16 incl. file chooser flows,
  cancel/reopen, URL dialog, playlist expansion, fullscreen cycle, video
  centering geometry, visualizer, honest Spotify refusal, zero uncaught JS
  exceptions.
* `pytest -m 'not media'`: 224 passed. `dpkg -V` clean; `sha256sum -c
  dist/SHA256SUMS` OK.

## Remaining limitations

* Gates 4–6 remain PARTIAL (full historical regression matrices not re-run
  on Qt; evidence added where executed).
* Spotify direct playback unsupported by design (DRM/API-bound).
* CASUNAT1/legacy start-up takes several seconds (extraction + libVLC).
* open.spotify.com unreachable from some networks → metadata lookup then
  fails honestly and points to the YouTube search.
