# Test report

## 2026-08-08

- Fast/unit suite: **49 passed, 6 deselected** (`pytest -q -m 'not media'`).
- Targeted source-resolution media test: **1 passed**; verified native
  `yuv420p` planes and source PTS from the fixture.
- The full long-running media/UI matrix is not claimed as passing yet. It
  requires the remaining playback, CASUNAT2 reconstruction and device tests.

## Release truth

Green unit tests do not close any release gate by themselves. Gate status is
tracked in `IMPLEMENTATION_REPORT.md`.
