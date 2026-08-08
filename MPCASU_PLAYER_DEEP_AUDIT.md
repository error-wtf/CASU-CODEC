# MPCASU player deep audit — 2026-08-08

This audit covers the current source tree, not the aspirational feature list.
`COMPLETE` requires a real backend, visible UI integration, error handling and
tests. A button or a status label alone is not evidence.

## Release blockers

| Area | Status | Evidence |
|---|---|---|
| In-process legacy backend | PARTIAL | `mpcasu_backend.py` calls libVLC through ctypes and binds a native surface, but has no event manager, buffering model or device abstraction. |
| Native CASU playback | MISSING | `CasuBackend` validates JSON then opens the referenced original media through libVLC. It has no CASU payload reader or renderer. |
| Real video presentation | PARTIAL | A Tk Canvas is used as the libVLC surface; the app does not verify a presented frame and still paints diagnostic text on that same canvas when idle. |
| Audio output | PARTIAL | Audio is delegated to libVLC; there is no enumerated device, output selection, latency, channel-layout or underrun model. |
| A/V clock | MISSING | Position is polled every 500 ms; no audio-master clock, event timestamps, drift measurement or correction exists. |
| Playback events | PARTIAL | Optional `libvlc_event_manager` registration now maps lifecycle events into backend state; time/position events, UI dispatch and platform validation remain. |
| Error presentation | PARTIAL | Some media-state errors are mapped, but decoder/output failures are not consistently surfaced with actionable technical details. |
| Seeking | PARTIAL | libVLC time seeking exists, but decoder flush, exact target verification and post-seek state reconstruction are absent. |
| Track selection | PARTIAL | Audio/video/SPU cycling exists, but selection is a cycle button rather than a complete named track model with language, codec, channels, default and forced metadata. |
| External subtitles | MISSING | No external subtitle load, parser, attachment or delay UI. |
| Chapters/frame step/A-B repeat | MISSING | No backend or UI implementation. |
| Audio presentation | PARTIAL | Audio mode is selected from probe metadata, but cover art rendering and real PCM waveform/FFT are unavailable. |
| Playlist | PARTIAL | Add/remove/save/load/double-click/next/previous work locally; no drag/drop, reorder, multi-select, queue policy, shuffle/repeat, metadata rows or persistence validation. |
| Library/navigation | MISSING | Sidebar entries still report `view not available in this release`; no indexed library, search, thumbnails or real views exist. |
| History/resume | MISSING | Session stores playlist, volume, mute, rate and geometry only; no current item, position, track selection or resume prompt. |
| Settings/hotkey persistence | MISSING | Shortcuts are hardcoded and preferences are absent. |
| Fullscreen/PiP/mini player | PARTIAL | Window fullscreen toggle exists; no overlay auto-hide, cursor timeout, PiP or dedicated mini-player state. |
| Responsive layout | PARTIAL | Three width modes hide panels, but minimum size is fixed at 980×620 and there is no tested compact/drawer/HiDPI behavior. |
| Converter integration | MISSING | Player can consume sidecars, but cannot launch/monitor native conversion jobs or display conversion reports. |

## Concrete correctness defects

1. `LibVLCBackend.open_source` contains two consecutive
   `libvlc_media_new_path` calls for local files. This is redundant and should
   be removed before further backend work.
2. The UI has two list widgets (`library` and `queue`) with duplicated state;
   selection and reordering can diverge because there is no playlist model.
3. Network sources set `current = None`, so position/history/next-item and
   media-information behavior cannot be consistent for URLs.
4. The playback controller changes state optimistically after calling the
   backend. It has no rollback or event-driven transition when libVLC rejects,
   buffers or asynchronously fails.
5. `PlaybackController.attach` does not perform an open/probe contract; the UI
   owns backend lifecycle and therefore cannot safely support backend fallback.
6. The video Canvas is both the embedded libVLC surface and the diagnostic
   drawing surface. This is not a clean renderer boundary and prevents a
   reliable “frame actually presented” acceptance test.
7. The 50 ms visual tick continuously redraws the Canvas even when the screen
   is static. This conflicts with the project’s event-driven/damage-tracking
   performance requirement.
8. The 500 ms poll is used for EOF and position, so timeline latency and EOF
   detection are bounded by polling rather than media events.
9. `CasuBackend` advertises `native_casu_payload: unavailable`; the player
   correctly avoids pretending otherwise, but this confirms CASU playback is
   not implemented.

## What is genuinely working

- No ffplay/VLC executable is used in the runtime path.
- Local legacy media is sent to an in-process libVLC backend.
- Source probing chooses VIDEO versus AUDIO presentation mode.
- Play/pause/stop/seek/volume/mute/rate and basic track cycling call real
  backend APIs.
- Manifest validation and source hash/size checks are fail-closed.
- Official branding assets are resolved from source, package and system paths.
- The fast automated suite currently passes (`36 passed, 5 deselected` in the
  latest run); this does not prove actual GUI/audio/video output.

## Required implementation order

1. Add a real `MediaSource`/playlist model and remove duplicated Listbox state.
2. Add a backend event bridge and explicit `LOADING/READY/BUFFERING/PLAYING/
   PAUSED/SEEKING/ENDED/ERROR` transitions with rollback.
3. Separate video surface, diagnostic overlay and audio presentation widgets;
   add a reproducible actual-frame smoke test.
4. Add device/track/chapter/subtitle models and selection menus.
5. Implement persistent history/resume/settings and a real library model.
6. Replace polling redraw with event-driven position updates and dirty-region
   rendering.
7. Only then connect the native CASU reader/state scheduler to the same
   playback contract.

Until the first three steps are tested with a real H.264/AAC fixture, MPCASU
must remain classified as a playback prototype rather than a finished player.
