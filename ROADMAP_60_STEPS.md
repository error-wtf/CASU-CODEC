# CASU / MPCASU — 60-step implementation roadmap

This roadmap is gate-ordered. A later group may start only when the preceding
gate has code, behavior tests, negative tests, build evidence, and an honest
entry in `RELEASE_GATE_STATUS.json`.

It reconciles the supplied recovery kit with `CASU_60_STEP_ROADMAP.md` and the
two byte-identical deep-research notes. Their additional requirements are
binding: a library-level libav/PyAV decoder adapter, version-adaptive libVLC,
runtime rather than extension-based compatibility, shared track/device/event
models, and artifact-specific third-party provenance before bundling codecs.

Current execution dashboard (evidence, not optimism):

- Steps 1–20: PASS — repository truth and source-resolution STRICT.
- Steps 21–32: PASS — CASUNAT2 key/tile/PCM, source deletion and byte seek.
- Steps 33–40: PARTIAL — streaming limits, recovery and 10k corruption run
  pass; broader property/network/parser campaigns remain.
- Steps 41–50: PARTIAL — independent native video/PCM/subtitle/chapter paths,
  clickable chapter timeline and instrumented sinks pass; real-device master
  clock, hotplug and long drift remain.
- Steps 51–56: PASS/PARTIAL — CLI and GUI share an atomic journaled job engine;
  queue isolation/retry, SQLite library, settings and dynamic controls exist.
  Hash-verified restart/resume, attached cover art and bounded metadata are wired
  into CLI/GUI/native playback; ASS/SSA source styling is retained beside a text
  fallback and rendered through native libass. Typed alpha-bounded PGS/DVD/DVB/
  XSub conversion/source-deletion/playback/seek passes; broader product and
  platform matrices remain.
- Steps 57–60: OPEN — responsive Qt migration and complete cross-platform
  playback/build/shipping matrices remain.

## Gate A — source-resolution STRICT

1. Resolve the repository root; inventory all supplied recovery/research documents, ZIP helpers, contracts and visual assets.
2. Record HEAD, dependency/build configuration, baseline tests and third-party provenance without changing release claims.
3. Separate the reduced preview/activity analyzer from STRICT naming and behavior.
4. Define exact rational source time (`pts`, numerator, denominator).
5. Define immutable canonical frame and plane-layout metadata.
6. Preserve active source samples while excluding decoder stride padding.
7. Support RGB24 and RGBA source layouts without color conversion.
8. Support YUV420P, YUV422P, and YUV444P plane geometry.
9. Preserve 10-, 12-, and 16-bit integer samples.
10. Preserve color range, primaries, transfer, matrix, and chroma location.
11. Decode presentation-order frames without an FPS filter; retain the tested FFmpeg adapter while adding a library-level PyAV/libav adapter.
12. Preserve VFR PTS and decoded duration where available.
13. Detect unsupported or changing decoder layouts and fail closed.
14. Map display/luma tiles exactly onto subsampled and packed planes.
15. Hash coordinates, geometry, format, layouts, metadata, and active bytes.
16. Emit HOLD only for exact canonical state identity.
17. Emit KEY_STATE for stream start and every canonical format change.
18. Store rational validity bounds in the STRICT state map.
19. Wire STRICT into the production analyze, CLI, and converter path.
20. Prove Gate A with sample-mutation, VFR, B-frame, fail-closed, compile, and package tests.

## Gate B — native CASUNAT2 codec

21. Freeze the CASUNAT2 header, feature flags, chunk headers, and footer contract.
22. Define bounded stream descriptors for video, audio, subtitles, chapters, and attachments.
23. Serialize complete canonical video key states losslessly.
24. Serialize exact plane-aware tile updates with base/new hashes.
25. Encode HOLD as state persistence without redundant pixel payload.
26. Encode canonical PCM blocks with exact time bases and stream identity.
27. Encode subtitle packets, chapter tables, metadata, and attachments.
28. Force key states at start, format changes, recovery boundaries, and bounded PTS intervals.
29. Write a real byte-offset seek index for every reconstructable target.
30. Reconstruct and hash-check arbitrary target frames from the nearest key state.
31. Round-trip video and PCM after deleting or renaming the source media.
32. Preserve CASUNAT1 read compatibility without calling it CASUNAT2.

## Gate C — integrity, recovery, and hostile-input safety

33. Introduce centralized reader limits before every allocation.
34. Add manifest, chunk, seek-index, and footer integrity coverage.
35. Validate offsets, lengths, stream types, regions, timestamps, and dependencies.
36. Write periodic verified recovery points and partial index snapshots.
37. Recover only a verified prefix and expose FULLY_VERIFIED/RECOVERED_PREFIX/FAILED.
38. Add deterministic corrupt/truncated/oversized/dependency-cycle fixtures.
39. Add property round-trips and mutation tests.
40. Run and document a bounded parser fuzz campaign with zero crashes or hangs.

## Gate D — native player and shared media model

41. Define a backend-neutral media protocol and lifecycle state machine.
42. Keep legacy libVLC playback isolated in a version-adaptive `LibVLCBackend` that accepts every source its actual runtime can open.
43. Implement `NativeCasuBackend` without libVLC inheritance or source extraction.
44. Build bounded tile-state, reconstruction, audio, and subtitle queues.
45. Implement audio-master A/V timing and monotonic video-only timing.
46. Implement transactional forward/backward/rapid seek with cache invalidation.
47. Present native frames and dirty regions through an instrumentable video sink.
48. Feed native PCM through an instrumentable bounded audio sink.
49. Prove pause/resume/EOF/error recovery and that no legacy tempfile is created.
50. Unify real track, chapter, subtitle, playback-event, error and audio-device descriptors across backends.

## Gate E — converter and product player

51. Extract converter jobs, profiles, progress, cancellation, reports, and journal into a shared engine.
52. Make CLI and GUI use the same strict/native conversion pipeline.
53. Implement real queue progress, cancel cleanup, retry, verify, and batch failure isolation.
54. Add SQLite library, incremental scanner, history, resume, favorites, and playlists.
55. Add effective persistent settings for playback, tracks, delay, library, and interface.
56. Build real track/subtitle/chapter/device menus; remove visible placeholders.
57. Migrate the UI incrementally to responsive Qt views while preserving backend behavior.
58. Use only the supplied CASU/MPCASU assets, uncropped and HiDPI-safe.
59. Run exact-runtime VLC parity plus native playback matrices, GUI smoke, clean wheel/Debian installs and generate bundled license/provenance artifacts.
60. Mark 1.0 complete only when every gate has reproducible evidence and no P0 item remains open.
