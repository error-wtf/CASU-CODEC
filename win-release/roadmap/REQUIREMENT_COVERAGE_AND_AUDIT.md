# REQUIREMENT COVERAGE + TOOL DEPENDENCY GRAPH + ROADMAP AUDIT

## Requirement coverage (each ledger REQ → implementation/test phase)

| REQ | Phase / WP | Test phase | Gate rule |
|-----|-----------|-----------|-----------|
| REQ-REF-001 (read-only) | all | session-start audit | `git status` after each phase |
| REQ-PURE-001 (frozen pure web) | WP-WEB-001 | SHA256 compare | packaging |
| REQ-PORT-001 (C++20/Qt6/MinGW) | M1 Foundation | build gate | — |
| REQ-PORT-002 (no runtime deps) | WP-PKG-001 | clean-prefix | packaging |
| REQ-PORT-003 (wine) | all | tests/wine | wine matrix |
| REQ-PORT-004 (no feature loss) | all | feature matrix | matrix check |
| REQ-PORT-005 (golden) | WP-CORE-007 | golden | compatibility |
| REQ-PLAYER-001..006 | M3 Player | wine | runtime |
| REQ-YT-001 (transport) | WP-YT-002 | unit + real CDN | wine |
| REQ-CONV-001 (converter GUI) | M4 | wine GUI | — |
| REQ-WEB-001/002 (web backend) | M5 | API + security | wine |
| REQ-WIN-001/002/003 (paths/audio/DPI) | M3/M4 | wine | — |
| REQ-PKG-001/002 (packaging/license) | M6 | clean-prefix + license audit | — |
| REQ-REL-001/002 (gate/repro) | M6 | gate script | — |
| REQ-DEV-001 (analysis first) | done (this phase) | docs + audit | — |

No orphan requirements.

## Tool dependency graph

```
casu_core ──┬─▶ casu_codec ──┬─▶ Converter
            ├─▶ casu_media ──┤
            │                 └─▶ MPCASU (playback path)
            └─▶ casu_playback ──▶ LibVLCBackend / NativeCasuBackend
casu_network ──┬─▶ MPCASU (network streams, YouTube transport)
               └─▶ casu_webapi ──▶ CASU-Web-Backend
casu_media ──▶ Converter
web/pure (frozen) ──▶ bundled into package
helpers: yt-dlp.exe, ffmpeg.exe, ffprobe.exe ──▶ QProcess from all apps
```

## Roadmap audit

- All tools in TOOL_INVENTORY covered: MPCASU, Converter, Web-Backend,
  Pure-Web, CLI, dev tools. ✓
- All features in WINDOWS_PORT_FEATURE_MATRIX have a WP. ✓
- Shared core (casu_core/…) planned once, no per-tool duplication. ✓
- Tests woven into every WP (unit→integration→cross-compile→wine→golden). ✓
- Read-only rule: only win-release/ written. ✓
- Web (pure + backend) fully included; converter fully included; CASU fully
  included. ✓
- No big-bang; always runnable intermediate (hello-exe → empty GUI → local MP4). ✓
- Wine used from STEP 001 (hello exe) onward. ✓
- No false PASS: every VERIFIED requires runtime evidence. ✓

## Blockers

- WP-BUILD-001 in progress; remaining environment gaps: Qt6 (MinGW) binaries +
  libVLC Windows binaries + ffmpeg/yt-dlp Windows binaries to bundle, and a
  Qt6 cross-deployment method. These are acquisition tasks, not design blockers.
