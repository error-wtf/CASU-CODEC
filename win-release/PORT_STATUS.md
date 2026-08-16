# PORT STATUS

| Field | Value |
|-------|-------|
| Current phase | **VORBEREITUNG FINAL** — Gesamtsystem + Start-Datei fertig (`START_HIER.md`); Beschaffungsliste (`PREREQUISITES.md`). Neuer Portierungs-Run startet mit SCHRITT 0 + STEP-001. |
| Current execution step | SCHRITT 0 (Prerequisites) + STEP-001 (WP-REL-001 toolchain: mingw64 + hello-exe + Wine) |
| Reference tree modified | NO (only AGENTS.md freeze doc + win-release/ added) |
| Baseline | HEAD `36df249`, 400 tests PASS |
| Pure Web Release | published (SHA in baseline) |

## Progress

- [x] Freeze + Pure Web Release (GitHub v2.0.0)
- [x] WINDOWS_PORT_BASELINE.md, audit/session-start.txt
- [x] PROMPT_REQUIREMENTS_LEDGER.md
- [x] repository-inventory.md, TOOL_INVENTORY.md, WINDOWS_PORT_FEATURE_MATRIX.md
- [x] casu-format-deep-dive.md
- [x] player-mechanics.md (+ state machines/lifecycle traps)
- [x] ui-style-bible.md (shared design tokens, provenance)
- [x] web-api-contract.md
- [x] windows-technology-map.md (linux-specific inventory + replacements)
- [x] design-history.md (why-things-are-the-way-they-are)
- [x] UNDERSTANDING_CHECK.md
- [x] MASTER_WINDOWS_PORT_ROADMAP.md
- [x] CRITICAL_PATH.md (incl. risk register + execution plan)

## Next steps

1. Commit/push per-tool roadmaps (this commit).
2. Set up build environment: verify/install `mingw-w64`, `cmake`, `ninja`,
   `wine`; obtain Qt6 (MinGW) + libVLC Windows binaries + ffmpeg/yt-dlp.exe.
3. Execute STEP 001: WP-REL-001 toolchain + hello-Windows-exe + Wine run.
4. Work the EXECUTION_PLAN phase by phase (Foundation → core libs → apps →
   packaging), one WP at a time, VERIFIED gates only.
