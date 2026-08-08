# CASU Converter deep audit — 2026-08-08

This audit treats the converter as a release product, not as a file picker.
The current implementation is intentionally honest about being a sidecar
analyzer, but it is not yet a native CASU converter.

## Executive result

The current converter performs:

```text
probe source
→ decode reduced video/audio activity with FFmpeg
→ build JSON timing hints
→ atomically write a .casu manifest
```

It does **not** perform:

```text
encode media payloads
→ write native CASU streams
→ build canonical tile state payloads
→ write key states/index/footer/recovery data
```

Therefore the product status is **COMPATIBILITY SIDECAR ANALYZER**, not
**CASU Native Converter**.

## Capability matrix

| Capability | Status | Evidence / problem |
|---|---|---|
| Single-file probe | PARTIAL | `ffprobe` returns streams and format, but only the first audio/video stream is analyzed. |
| Video analysis | PARTIAL | Reduced 160×90 grayscale activity hints; no canonical planes or per-tile payload. |
| Audio analysis | PARTIAL | Chunked mono RMS analysis; no preserved audio stream, channels, layout, gapless data or waveform cache. |
| Strict lossless | MISSING | Current strict mode is fail-closed metadata policy, not exact source-to-CASU conversion. |
| Native `.casu` output | MISSING | Output is UTF-8 JSON referencing the original file. |
| Metadata preservation | PARTIAL | Basic stream fields are copied; tags, chapters, attachments, cover art, language/default/forced flags and full provenance are not preserved. |
| Multi-stream handling | MISSING | No per-stream conversion model for multiple video/audio/subtitle/data streams. |
| Subtitles/chapters | MISSING | Not analyzed or written as converter-owned data. |
| Batch queue | MISSING | GUI accepts one source and one output only. |
| Pause/cancel | MISSING | Worker is a daemon thread with no cancellation token; FFmpeg cannot be terminated by the user. |
| Progress/ETA | MISSING | GUI uses an indeterminate progress bar; core exposes no progress callback or phase. |
| Profiles/presets | MISSING | Only mode and analysis FPS exist; no documented technical conversion profiles. |
| Dry-run/analyze view | PARTIAL | CLI `analyze` writes a manifest; GUI inspection only shows a short probe summary. |
| Verify | PARTIAL | Structural validation and source hash/size verification exist; no native payload/index/segment verification. |
| Repair/recovery | MISSING | No repair command, resumable journal, recovery state or interrupted-job recovery. |
| Reports | PARTIAL | Benchmark JSON reports elapsed analysis and counts; no per-file conversion report, CSV/Markdown export or phase metrics. |
| Benchmark | PARTIAL | Measures analysis wall time only; does not compare legacy vs CASU decode/render/storage or memory traffic. |
| Crash safety | PARTIAL | Atomic final manifest writes are safe; worker crashes, orphan process cleanup and resumable jobs are absent. |
| Determinism | PARTIAL | JSON ordering is stable enough for normal runs, but absolute source paths and environment/tool versions make byte identity non-portable. |
| Security bounds | PARTIAL | Manifest bounds and safe subprocess argument lists exist; decoder resource limits, timeouts and output quotas are absent. |
| CLI automation | PARTIAL | `analyze`, `convert`, `validate`, `verify`, `info`, `benchmark` exist; no batch manifest, job database or machine-readable progress stream. |
| GUI branding | COMPLETE | Supplied CASU logo/icon are resolved and packaged. |
| GUI product workflow | MISSING | Tk window has no queue, phase view, report panel, cancel, retry, verify or batch controls. |
| Tests | PARTIAL | Core manifest/analyzer tests exist; no converter GUI, cancellation, progress, crash, multi-stream or native round-trip tests. |

## Concrete implementation risks

1. The converter’s `threading.Thread(..., daemon=True)` continues after the
   window is closed. There is no cooperative stop and no guaranteed FFmpeg
   child cleanup.
2. Both video and audio analysis use `stderr=PIPE` but do not drain stderr
   concurrently while consuming stdout. A sufficiently verbose FFmpeg error
   stream can block the child process.
3. There is no timeout, memory limit, output-size limit, decode-frame limit or
   maximum duration guard for hostile or simply enormous inputs.
4. The GUI progress bar cannot distinguish probing, video analysis, audio
   analysis, validation and atomic finalization, and cannot calculate ETA.
5. `analyze()` runs video and audio passes sequentially from the beginning of
   the source. A long file is decoded twice and cannot resume after interruption.
6. The GUI “Convert” action writes a sidecar regardless of the selected mode;
   mode changes hint thresholds only and never change encoded output.
7. The CLI default output is `input.<suffix>.casu`, while the GUI defaults to
   `input.<suffix>.casu`; there is no shared output naming/profile policy.
8. The manifest records an absolute source path. The basename fallback is safe,
   but portable conversion packages should make provenance path policy explicit
   and avoid treating a machine-local path as portable identity.
9. No embedded source copy, stream payload, key-state, index, footer or
   recovery marker means a `.casu` file is unusable without the original media.
10. The Debian package installs a small Tk GUI but does not provide a native
    conversion runtime or a test corpus; package installation therefore cannot
    prove conversion correctness.

## Required converter architecture

```text
MediaSource / Probe
        ↓
ConversionJob + Profile
        ↓
Decode workers (cancellable, bounded, progress events)
        ↓
Canonical video/audio/subtitle stream model
        ↓
Tile state engine + native CASU payload writer
        ↓
Index / key states / integrity / recovery
        ↓
Atomic finalization + ConversionReport
```

The GUI and CLI must consume the same job engine. The GUI must not duplicate
conversion logic.

## Release gates

The converter must not be called complete until all of these are demonstrated:

1. Two-file and recursive batch jobs with persistent queue state.
2. Real progress phases, ETA where measurable, pause/cancel and retry.
3. Clean cancellation that terminates decoder children and removes temporary
   incomplete outputs.
4. Native CASU writer/reader round-trip for video, audio, subtitles, metadata
   and timestamps.
5. Exact strict-mode comparison against a canonical reference and a negative
   test that detects a one-byte tile change.
6. Verify/info/repair reports for valid, truncated, corrupt and tampered files.
7. Deterministic JSON/CLI reports including tool and profile versions, without
   claiming energy savings that were not measured.
8. CLI and GUI integration tests using small generated fixtures, with long
   media tests explicitly marked slow.

Until these gates pass, the correct user-facing label is “CASU sidecar
analysis/conversion prototype”.
