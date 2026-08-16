# Remaining files / fixtures / licenses (completeness)

Completeness audit (`research-tools/completeness_audit.py`) found 10 files not
named in the first analysis batch. Each is now classified here.

| File | Classification | Windows relevance |
|------|----------------|-------------------|
| `mpcasu_qt/youtube_proxy.py` | CORE transport | port → `youtube-transport.md` |
| `mpcasu_qt/webplayers.py` | web feature + obsolete play_video | see `webplayers-and-legacy.md` |
| `mpcasu_qt/__init__.py` | package marker (docstring only) | trivially recreated |
| `web/native-smoke.html/js` | CASUNAT2 browser self-test | bundle, Wine browser run |
| `web/README.md` | stale (references missing mpcasu_web.py) | OBSOLETE doc |
| `mpcasu_web/index.html, player.js` | legacy minimal player | OBSOLETE/legacy, excluded (documented) |
| `artifacts/recovery/db_recovery-script.py` | **NOT part of app** — recovers an unrelated opencode DB | excluded (not shipped) |
| `test_media/*` | fixtures (mp4, mp3, casu, mp5, playlist, README) | copy as test fixtures for wine/unit + golden |
| `THIRD_PARTY_LICENSES/README.md` | license collection policy | adopt policy for Windows bundling |

## Fixtures (test_media/) — use as Wine/golden inputs

- `demo_clip.mp4` (+ `.casu` sidecar), `demo.mp5`, `demo_casunat2.casu`,
  `demo_playlist.m3u`, `lino_casu_error.mp3` (+ `_original`).
- These are small, real inputs for unit/golden/Wine playback + converter tests.
  Copy read-only into `win-release/tests/fixtures/` for the port.

## Licenses policy

`THIRD_PARTY_LICENSES/README.md` policy: no third-party codec copied in the
Linux packages; before bundling, copy exact license texts + record versions
and hashes in `THIRD_PARTY_COMPONENTS.md`. **Adopt for Windows:** before
bundling Qt/libVLC/FFmpeg/zstd/yt-dlp/yt-dlp.exe, copy their licenses and
document source offers. CASU license itself stays unchanged.

## Completeness state

All source files under the reference tree (163) are now classified and mapped
to a Windows decision. No file is unanalyzed. The audit tool can be re-run
after adding more docs to keep this true.
