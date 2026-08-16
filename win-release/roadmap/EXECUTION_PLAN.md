# EXECUTION PLAN — Windows Port (per-tool WPs, ordered by dependencies)

Each STEP references concrete WPs. Work one WP at a time: reference re-read →
implement (win-release only) → cross-compile → unit → wine → compat → VERIFIED.

## Phase A — Foundation (shared, blocks everything)
```
STEP 001  WP-REL-001 toolchain (mingw64 + hello-exe + Wine run)        [CRITICAL]
STEP 002  WP-REL-002 top-level CMake modular targets + deps + packaging.cmake
STEP 003  WP-REL-003 build-windows-release.sh skeleton
STEP 004  WP-REL-004 DLL audit + WP-REL-005 clean-prefix harness + WP-DEV-000 wine harness
STEP 005  WP-REL-007 licenses audit (adopt policy)
```

## Phase B — Shared core libraries (M2)
```
STEP 006  WP-CORE-001 container primitives
STEP 007  WP-CORE-002 manifest/limits
STEP 008  WP-CORE-003 CASUNAT1, WP-CORE-004 CASUNAT2, WP-CORE-005 MP5
STEP 009  WP-CORE-006 sidecar/metadata/tiles, WP-CORE-007 zstd
STEP 010  WP-CORE-008 golden fixtures (from reference)
STEP 011  WP-CODEC-001..005, WP-MEDIA-001..005
STEP 012  WP-NET-001..005
STEP 013  WP-PLAY-001..005
STEP 014  WP-WEBAPI-001..005
```

## Phase C — Apps (by dependency: CLI → Converter → MPCASU → Web-Backend)
```
STEP 015  WP-CLI-000 framework + WP-CLI-001..015 (per subcommand) + 016
STEP 016  WP-CONV-001..002 GUI foundation
STEP 017  WP-CONV-010..022 core + CASU import/export
STEP 018  WP-CONV-030..032 progress/cancel/errors/output
STEP 019  WP-MPCASU-001..013 app+UI+playback core
STEP 020  WP-MPCASU-020..023 playback core (shared casu_playback already done)
STEP 021  WP-MPCASU-030..035 playlist/library/settings/EPG/viz/recording
STEP 022  WP-MPCASU-040..042 YouTube
STEP 023  WP-MPCASU-050..052 providers/input/shutdown
STEP 024  WP-WEB-001..003 web backend HTTP+security
STEP 025  WP-WEB-010..017 API endpoints
STEP 026  WP-WEB-020..030 lifecycle + packaging
STEP 027  WP-PURE-001..005 pure-web integration
```

## Phase D — Packaging + Release gate (M6)
```
STEP 028  WP-CONV-040, WP-MPCASU-060, WP-WEB-030 package into zip
STEP 029  WP-REL-005 clean-prefix package test
STEP 030  WP-REL-006 WINDOWS_RELEASE_GATE.json + WP-REL-008 sha256/repro
```

## Definition of done
All TOOL_PORT_STATUS rows VERIFIED (or documented EXCLUDED). Gate JSON all
PASS. Reference tree untouched. Release zip + SHA256 produced.

## Blockers (tracked in roadmap/BLOCKERS.md)
- Qt6 MinGW binaries + libVLC Windows binaries + ffmpeg/yt-dlp Windows to
  bundle (acquisition, not design).
