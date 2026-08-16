# Dev / Diagnostic Tools — Windows Port Roadmap (TOOL-SMOKE*, SCREENSHOT*, FUZZ, RELEASE-GUARD)

Reference: `tools/` (16 scripts). Each is classified PORT / REPLACE /
KEEP-LINUX-ONLY / OBSOLETE. Never silently deleted (REQ-PORT-004).

## Classification + per-tool plan

| Tool | Entry | Class | Windows plan | WP |
|------|-------|-------|--------------|----|
| smoke_qt_sources.py | GUI nav/sources smoke | REPLACE | Wine GUI smoke (Qt) | WP-DEV-001 |
| smoke_qt_playback.py | playback smoke | REPLACE | Wine playback smoke | WP-DEV-002 |
| smoke_qt_playlist.py | playlist smoke | REPLACE | Wine playlist smoke | WP-DEV-003 |
| smoke_backends.py | backend probes | REPLACE | C++ backend unit+wine | WP-DEV-004 |
| smoke_owner_casu.py | CASU owner smoke | REPLACE | casu_core unit | WP-DEV-005 |
| smoke_session4.py | session smoke | REPLACE | Wine session | WP-DEV-006 |
| smoke_web_nav.py | web nav smoke | KEEP (web) | reuse with web backend | WP-DEV-007 |
| smoke_web_playlist.py | web playlist smoke | KEEP (web) | reuse | WP-DEV-008 |
| acceptance_qt.py | Qt acceptance | REPLACE | Wine acceptance | WP-DEV-009 |
| acceptance_web.py | web acceptance | KEEP (web) | reuse | WP-DEV-010 |
| screenshot_cli/converter/qt/web.py | screenshot gates | REPLACE/ADAPT | Wine screenshot gates | WP-DEV-011 |
| fuzz_native_v2.py | CASUNAT2 fuzz | PORT | C++ fuzz test (native_v2) | WP-DEV-012 |
| release_gate_guard.py | release gate | REPLACE | Windows gate script | WP-DEV-013 |

## WP-DEV-000 shared wine-test harness
- PURPOSE: isolated WINEPREFIX (.wine-test), wineboot, xvfb-run wrapper,
  log capture (stdout/stderr/wine/app/libVLC/ffmpeg/yt-dlp), result JSON.
- ACCEPTANCE: reusable by all tools. STATUS: NOT_STARTED.

## Per-tool WPs follow the standard shape
PURPOSE / REFERENCES / OUTPUT / UNIT / WINE / COMPATIBILITY / ACCEPTANCE /
STATUS. All dev tools must never depend on the build machine's PATH/DLLs
(clean-prefix discipline).
