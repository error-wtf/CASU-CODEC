# CASU-CLI — Windows Port Roadmap (Tool: TOOL-CASU-CLI)

Entry (reference): `python3 -m casu` → `casu/cli.py` (601 lines) +
`casu/__main__.py`. Windows artifact: **`casu.exe`** (C++ CLI; shares
casu_core/codec). Exit codes, stdout/stderr and JSON outputs must be
compatible (REQ-PORT-004).

Reference map: casu/cli.py (argparse subcommands), casu/core.py (analyze/
play/resolve), native.py, native_v2, mp5, jobs.py (ConversionEngine),
export.py, filetypes.py, transcode.py, probe.py.

## Subcommands (from cli.py) — one WP each

| Subcommand | Purpose | WP |
|------------|---------|----|
| analyze | write CASU temporal-state sidecar | WP-CLI-001 |
| convert | convert legacy media to CASU (sidecar/native/native-v2) | WP-CLI-002 |
| pack | standalone CASUNAT1 (lossless payload) | WP-CLI-003 |
| pack-v2 | segmented CASUNAT2 | WP-CLI-004 |
| pack-mp5 | CASU MP5 container | WP-CLI-005 |
| mp5-info | verify/inspect MP5 | WP-CLI-006 |
| native-info | verify/inspect native CASU | WP-CLI-007 |
| repair-v2 | finalize declared CASUNAT2 prefix | WP-CLI-008 |
| export | CASU → FFmpeg-supported media | WP-CLI-009 |
| media | media subcommands | WP-CLI-010 |
| play | validate a media path for in-process playback | WP-CLI-011 |
| validate | validate a .casu manifest | WP-CLI-012 |
| verify | validate + verify recorded source | WP-CLI-013 |
| info | machine-readable manifest info (JSON) | WP-CLI-014 |
| benchmark | deterministic analysis cost JSON report | WP-CLI-015 |

## WP structure per subcommand
- PURPOSE / REFERENCES (exact cli.py lines) / INPUT flags+defaults /
  OUTPUT (stdout/stderr/JSON/exit code) / TARGET FILES (casu/cli_*.cpp) /
  UNIT (flag parsing, exit codes) / WINE (run each subcommand on fixtures,
  compare stdout+exit vs Linux) / COMPATIBILITY (JSON + exit codes identical)
  / ACCEPTANCE / STATUS.

## CLI-general WPs
- WP-CLI-000 argparse-equivalent CLI framework in C++ (flags, defaults,
  subparsers, help), Unicode Windows paths.
- WP-CLI-016 journal/resume for convert batch (jobs journal path).
- WP-CLI-020 Packaging: bundle casu.exe + tools/ffmpeg|yt-dlp in zip.

## Compatibility gate
For each subcommand: Linux `python3 -m casu …` vs Wine `casu.exe …` on the
same fixtures → identical stdout/stderr (semantic) + identical exit codes +
identical output files (hashes where deterministic).
