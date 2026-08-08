<!-- SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4 | SPDX-FileCopyrightText: 2026 Lino Casu -->
# MPCASU implementation audit

This inventory is deliberately conservative. A visible control is not counted
as complete unless the underlying behavior is implemented and exercised.

## Reference reconciliation (2026-08-08)

The supplied `CODEX_MASTER_PROMPT_CASU_MPCASU.txt` and
`CODEX_MPCASU_CASU_MASTER_IMPLEMENTATION_GUIDE.md` define the target state,
not the exact state of every current commit. Some findings in older copies of
that guidance are now stale:

| Older claim | Current evidence | Correct interpretation |
|---|---|---|
| `strict_pixel_identical_available` is true | `casu/core.py` sets it to `False` and labels reduced analysis non-identity proof | The strict gate is still **OPEN**, but it is now fail-closed. |
| All analysis modes use one algorithm | `analyze_video(..., mode=...)` receives the selected mode and applies distinct thresholds | Modes differ as hint policies; none is a lossless spatial state map. |
| Audio analysis buffers the entire decoded stream | `analyze_audio` consumes fixed-size `Popen` chunks | Memory scaling is improved; cancellation/progress is still missing. |
| Scheduler is a linear scan | `CasuScheduler` uses sorted starts and `bisect_right` | Lookup is logarithmic, but this is still metadata scheduling, not native tile runtime. |
| libVLC only supports one Linux/X11 path | Library candidates and Linux/Windows/macOS surface setters exist | Deployment and event integration still need platform tests. |

The following remain release blockers:

1. `.casu` is a validated JSON sidecar referencing original media; no native
   payload reader/writer, tile payload, key-state index, footer, recovery chain,
   or native renderer path exists.
2. `analyze_video` operates on a reduced grayscale preview and produces hints,
   not canonical `S(x,y,t)` tile states or exact HOLD proofs.
3. The player still has placeholder navigation, a Tkinter monolith,
   polling-based observation, and no complete library/history, chapters,
   external subtitles, audio-device, mini-player, or settings model.
4. The converter remains a single-source Tk front end with indeterminate
   progress; batch queue, cancellation, resumable jobs, reports, and native
   CASU output are not implemented.

`FORMAT_SPEC.md` and `README(8).md` describe the historical SSC/sidecar
compatibility layer. They are provenance inputs, not the missing native CASU
1.0 container. `CASU_FORMAT_SPECIFICATION.md` is the repository truth and
intentionally records that boundary.

## Runtime architecture

| Area | Status | Evidence / boundary |
|---|---|---|
| In-process media backend | **PARTIAL** | `mpcasu_backend.py` uses libVLC through `ctypes`; open/play/pause/stop/seek, position, duration, rate, volume and cross-platform library/surface selection are wired. |
| External player process | **REMOVED** | Production MPCASU no longer launches `ffplay` or another player executable. |
| CASU validation and source integrity | **COMPLETE** | Manifest schema and SHA-256 source verification run before CASU playback. |
| Native CASU state scheduler | **MISSING** | Current `.casu` is a validated sidecar; segment states are diagnostic hints, not yet a renderer scheduler. |
| Shared media clock | **PARTIAL** | Backend position is polled from libVLC; explicit audio-master clock, event callbacks and drift correction remain. |
| Embedded video surface | **PARTIAL** | libVLC targets the MPCASU Tk canvas window on Linux; color/HDR/HiDPI policy is not complete. |
| Official player icon asset | **COMPLETE** | `assets/mpcasu_player_icon.png` is packaged and used for the application icon when Pillow is available. |
| Internal audio output | **PARTIAL** | libVLC owns decoding/output, but MPCASU does not yet expose a separate audio device pipeline. |

## User-facing capabilities

| Capability | Status | Current behavior |
|---|---|---|
| Play / pause / stop | **PARTIAL** | Real libVLC controls; cross-platform state/event handling still needs expansion. |
| Seek | **PARTIAL** | Real backend seek and buffer reset through libVLC; exact target-frame verification is pending. |
| Playlist add/remove/double-click | **PARTIAL** | Works for local files and CASU manifests; persistence, reorder and drag/drop are pending. |
| Keyboard transport | **PARTIAL** | Space, arrows and Escape are wired; configurable media keys are pending. |
| Fullscreen | **PARTIAL** | Window fullscreen toggle exists; dedicated overlay/cursor timeout is pending. |
| Volume / mute | **PARTIAL** | Real libVLC volume/mute calls and keyboard controls exist; device routing and persisted output selection remain. |
| Audio/video/subtitle track selection | **PARTIAL** | Audio and optional subtitle track cycling use real libVLC APIs; named track models and video-track UI remain. |
| Chapters / frame-step / A-B repeat | **MISSING** | No visible fake controls are advertised. |
| External subtitles | **MISSING** | Parser/overlay integration is not yet implemented. |
| Audio mode / cover art / FFT | **PARTIAL** | Stream-derived audio mode and attached-cover-art detection exist; PCM waveform/FFT is intentionally unavailable. |
| Library/history/resume | **MISSING** | Current list is session-local only. |
| Settings/hotkey persistence | **MISSING** | Not claimed by the current 1.0 slice. |
| Network streams | **PARTIAL** | URL dialog and libVLC URL backends support common schemes; buffering/error events and network library UI remain. |
| CASU diagnostics | **PARTIAL** | Validated segment map can be displayed; active/held/updated render accounting is pending. |
| Energy measurement | **MISSING** | UI explicitly says telemetry unavailable. |
| Integrity state | **PARTIAL** | Manifest/source digest validation exists; runtime frame/output integrity is pending. |

## Test coverage

The current automated suite covers manifest validation, source digest/size
guardrails, analyzer output and GUI playlist smoke behavior. It does **not** yet
prove the complete format matrix, A/V drift, subtitles, hardware decode,
network playback, or long-running performance. Those are release gates for a
future full MPCASU release, not silently upgraded claims for this build.

## Release interpretation

The Debian packages are an installable development release of the CASU codec,
converter and MPCASU player. They are not described as feature-complete VLC
replacement software. This file must be updated whenever a partial or missing
capability becomes genuinely implemented and tested.

## Next acceptance gates

Implementation is deliberately narrowed to the CASU core before more cosmetic
features are added:

| Gate | Required evidence |
|---|---|
| P0.1 Exact tile comparison | Canonical decoded planes/tiles, deterministic color handling, and tests proving identical versus changed tiles. |
| P0.2 Spatial-temporal state map | Persisted tile coordinates, timestamps, lifecycle, reference hashes and fidelity policy; aggregate ratios are not a substitute. |
| P0.3 Runtime scheduler | Key states, dependency/invalidation rules, seek index, bounded cache and deterministic reconstruction tests. |
| P0.4 Native CASU I/O | Versioned reader/writer with payload, index, integrity and recovery sections, plus a backend path independent of the source file. |

Until all four gates pass, CASU remains a compatibility sidecar and MPCASU
remains a legacy-playback prototype. This is an explicit status boundary, not
a dismissal of the packaging, safety and playback repairs already completed.
