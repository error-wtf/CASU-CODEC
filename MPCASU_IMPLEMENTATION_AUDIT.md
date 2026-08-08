<!-- SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4 | SPDX-FileCopyrightText: 2026 Lino Casu -->
# MPCASU implementation audit

This inventory is deliberately conservative. A visible control is not counted
as complete unless the underlying behavior is implemented and exercised.

## Runtime architecture

| Area | Status | Evidence / boundary |
|---|---|---|
| In-process media backend | **PARTIAL** | `mpcasu_backend.py` uses libVLC through `ctypes`; open/play/pause/stop/seek, position and duration are wired. |
| External player process | **REMOVED** | Production MPCASU no longer launches `ffplay` or another player executable. |
| CASU validation and source integrity | **COMPLETE** | Manifest schema and SHA-256 source verification run before CASU playback. |
| Native CASU state scheduler | **MISSING** | Current `.casu` is a validated sidecar; segment states are diagnostic hints, not yet a renderer scheduler. |
| Shared media clock | **PARTIAL** | Backend position is polled from libVLC; explicit audio-master clock and drift correction remain. |
| Embedded video surface | **PARTIAL** | libVLC targets the MPCASU Tk canvas window on Linux; color/HDR/HiDPI policy is not complete. |
| Internal audio output | **PARTIAL** | libVLC owns decoding/output, but MPCASU does not yet expose a separate audio device pipeline. |

## User-facing capabilities

| Capability | Status | Current behavior |
|---|---|---|
| Play / pause / stop | **PARTIAL** | Real libVLC controls; cross-platform state/event handling still needs expansion. |
| Seek | **PARTIAL** | Real backend seek and buffer reset through libVLC; exact target-frame verification is pending. |
| Playlist add/remove/double-click | **PARTIAL** | Works for local files and CASU manifests; persistence, reorder and drag/drop are pending. |
| Keyboard transport | **PARTIAL** | Space, arrows and Escape are wired; configurable media keys are pending. |
| Fullscreen | **PARTIAL** | Window fullscreen toggle exists; dedicated overlay/cursor timeout is pending. |
| Volume / mute | **MISSING** | UI reports unavailable rather than showing a fake value. |
| Audio/video/subtitle track selection | **MISSING** | Stream enumeration and selection UI are not yet exposed. |
| Chapters / frame-step / A-B repeat | **MISSING** | No visible fake controls are advertised. |
| External subtitles | **MISSING** | Parser/overlay integration is not yet implemented. |
| Audio mode / cover art / FFT | **MISSING** | No fake spectrum or metadata is shown. |
| Library/history/resume | **MISSING** | Current list is session-local only. |
| Settings/hotkey persistence | **MISSING** | Not claimed by the current 1.0 slice. |
| Network streams | **MISSING** | Local path support only. |
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
