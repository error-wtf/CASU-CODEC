# CASU-Converter — Windows Port Roadmap (Tool: TOOL-CONVERTER)

Entry (reference): `python3 casu_converter.py` (Tk GUI, 1061 lines) +
`casu/jobs.py` (ConversionEngine) + `casu/transcode.py` (FFmpeg presets).
Windows artifact: **`CASU-Converter.exe`** (Qt 6 C++ GUI).

Reference map:
- `casu_converter.py` (GUI, batch, progress, cancel, CASU import/export)
- `casu/jobs.py` (ConversionEngine: run/_convert/_load_resume/_journal/notify/
  abort; ConversionJob, ConversionProfile, ConversionResult,
  ConversionProgressTracker)
- `casu/transcode.py` (MEDIA_PRESETS {remux,balanced,high,small,lossless},
  MEDIA_OUTPUT_EXTENSIONS, quality options, ffmpeg argument builder)
- `casu/filetypes.py` (detect_casu_kind), `casu/export.py` (export_casu),
  `casu/core.py` (analyze, ANALYSIS_MODES)
- `casu/native.py`, `casu/native_v2/`, `casu/mp5/` (pack formats)
- research: casu-format-deep-dive, ui-style-bible, api-contracts-errors-shutdown

NOTE: `casu_converter.py` is the **GUI**; the CLI `convert` subcommand is
covered under TOOL-CASU-CLI. The Windows Converter is a full GUI (not CLI-only,
REQ-CONV-001).

Status legend: NOT_STARTED / ANALYSIS / IMPLEMENTING / BUILDING / TESTING /
WINE_TESTING / BLOCKED / VERIFIED.

================================================================
M-CONV-1 — GUI FOUNDATION
================================================================

## WP-CONV-001 Qt application skeleton (window, style)
- PURPOSE: `CASU-Converter.exe` window, red/black design tokens.
- REFERENCE: casu_converter.py layout, ui-style-bible.md.
- WINE: window appears, no missing DLLs. STATUS: NOT_STARTED.

## WP-CONV-002 Input selection + drag & drop
- REFERENCE: casu_converter.py file dialogs/drop; Windows paths, Unicode,
  long paths. WINE: open files with spaces/Unicode. STATUS: NOT_STARTED.

================================================================
M-CONV-2 — CORE CONVERSION (shared casu_codec + casu_media)
================================================================

## WP-CONV-010 Probe + source validation (ffprobe.exe)
- REFERENCE: casu/probe.py; QProcess ffprobe. WINE: probe real files.
- STATUS: NOT_STARTED.

## WP-CONV-011 FFmpeg presets + arg builder
- REFERENCE: casu/transcode.py (presets/quality/extension). QProcess arg
  arrays (no shell strings). WINE: convert small + large + Unicode.
- STATUS: NOT_STARTED.

## WP-CONV-012 Batch engine
- REFERENCE: casu/jobs.py ConversionEngine (run/notify/abort/journal/resume).
  Output layout preserves relative paths; journal for resume.
- WINE: batch convert, resume, cancel. STATUS: NOT_STARTED.

================================================================
M-CONV-3 — CASU IMPORT/EXPORT + FORMATS
================================================================

## WP-CONV-020 CASU encode (sidecar / CASUNAT1 / CASUNAT2 / MP5)
- REFERENCE: casu/core.py analyze, native.py, native_v2, mp5. Golden fixtures.
- STATUS: NOT_STARTED.

## WP-CONV-021 CASU decode/export
- REFERENCE: casu/export.py, verify. STATUS: NOT_STARTED.

## WP-CONV-022 Formats MP4/MP3/legacy + metadata + thumbnails/cover
- REFERENCE: casu/transcode.py, tags.py, thumbnail.py. STATUS: NOT_STARTED.

================================================================
M-CONV-4 — PROGRESS / CANCEL / ERRORS / OUTPUT
================================================================

## WP-CONV-030 Progress bar + cancel (worker thread → GUI)
- REFERENCE: ConversionProgressTracker, jobs.notify/abort.
- WINE: progress updates, cancel stops ffmpeg cleanly. STATUS: NOT_STARTED.

## WP-CONV-031 Output dir + overwrite handling + temp cleanup
- REFERENCE: casu_converter.py, jobs. WINE: overwrite, no leftover temp.
- STATUS: NOT_STARTED.

## WP-CONV-032 Error reporting (typed → user messages)
- REFERENCE: api-contracts-errors-shutdown.md. STATUS: NOT_STARTED.

================================================================
M-CONV-5 — PACKAGING + WINE VALIDATION
================================================================

## WP-CONV-040 Bundle into Windows zip + clean-prefix Wine run
- REFERENCE: packaging plan. STATUS: NOT_STARTED.

## WINE matrix (converter): start, drag&drop, convert, cancel, batch,
Unicode path, space path, large file, error case, export→replay.

## Behavioral compatibility
Same input → same/semantically-identical output as Linux reference
(presets, manifest, checksums, segmentation). Golden tests (casu core).
GUI look preserved (shared tokens). Never CLI-only.
