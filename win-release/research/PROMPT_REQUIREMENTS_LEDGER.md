# Prompt Requirements Ledger

Consolidated, binding requirements from the Windows-port task. Each has an ID,
category, affected components, priority and verification. **REQ-REF-001 and
REQ-PURE-001 are never to be violated.**

| ID | Category | Requirement | Affected | Priority | Verification |
|----|----------|-------------|----------|----------|--------------|
| REQ-REF-001 | Reference tree | Existing Linux/Web code stays READ ONLY; never modified | everything outside `win-release/` | MUST NEVER VIOLATE | `git status --short` + diff audit after every phase |
| REQ-PURE-001 | Pure Web | PURE WEB release is frozen; byte-identical copy under `win-release/web/pure` | pure-web | MUST NEVER VIOLATE | SHA256 comparison |
| REQ-PORT-001 | Target stack | C++20 + Qt 6 + CMake + Ninja + MinGW-w64; Windows x86_64; cross-compiled under Linux | build system | MUST | build gate |
| REQ-PORT-002 | Runtime | No Python / Node / user-installed Qt/VLC required at runtime; self-contained package | packaging | MUST | clean Wine prefix test |
| REQ-PORT-003 | Testing | Every Windows binary tested under Wine (isolated prefix) | tests/wine | MUST | wine test matrix |
| REQ-PORT-004 | Feature parity | No silent feature loss; BLOCKED with reason instead | feature matrix | MUST | full feature matrix |
| REQ-PORT-005 | Golden | Codec output semantically identical to reference | codec | MUST | golden fixtures Linux↔Windows |
| REQ-PLAYER-001 | Player | Single player path: UI → PlaybackController → Backend → VideoSurface | mpcasu | MUST NEVER VIOLATE | architecture + wine runtime |
| REQ-PLAYER-002 | YouTube | YouTube = yt-dlp resolver → optional transport → LibVLCBackend → PlaybackController → VideoSurface; NO second player/browser/iframe | youtube, playback | MUST NEVER VIOLATE | wine runtime (real YouTube) |
| REQ-PLAYER-003 | VideoSurface | libVLC owns native surface; no Qt overlay on video; no flicker | videoframe | MUST | wine GUI test |
| REQ-PLAYER-004 | NOW PLAYING | "NOW PLAYING" stays a fixed heading; dynamic title in separate label outside video surface | main_window UI | MUST | UI/wine test |
| REQ-PLAYER-005 | libVLC | libVLC via C API in-process; `set_hwnd`; never external vlc.exe | backend | MUST | wine test |
| REQ-PLAYER-006 | Lifecycle | No premature stop()/double-close/dangling resources; clean shutdown order | backend/controller | MUST | wine + leak tests |
| REQ-YT-001 | Transport | Loopback proxy: GET/HEAD, Range, 206, Content-Length/Range, Accept-Ranges, no full-RAM buffering, loopback only, token path | youtube transport | MUST | unit + real CDN |
| REQ-CONV-001 | Converter | Full GUI converter (batch, formats, progress, cancel, metadata, CASU import/export), not CLI-only | converter | MUST | wine GUI |
| REQ-WEB-001 | Web backend | web-casu API reimplemented natively; frontend unchanged; API contract preserved | web-backend | MUST | API contract tests |
| REQ-WEB-002 | Web security | Loopback only; host validation; no 0.0.0.0; path traversal/upload/Range safety | web-backend | MUST | security tests |
| REQ-WIN-001 | Windows paths | Spaces, Unicode, long paths everywhere (QString/std::filesystem, QProcess arg arrays) | all tools | MUST | wine path tests |
| REQ-WIN-002 | Audio | No PulseAudio; Windows-native audio (WASAPI/Qt) | player/native | MUST | wine audio |
| REQ-WIN-003 | DPI | Qt DPI scaling tested (100/125/150/200%) | GUI | MUST | wine screenshots |
| REQ-PKG-001 | Packaging | Portable `MPCASU-Windows-x86_64.zip`: exes, Qt DLLs, qwindows plugin, vlc + plugins, tools (ffmpeg/yt-dlp), web/, licenses, README | packaging | MUST | clean-prefix package test |
| REQ-PKG-002 | Licenses | Redistribution/licenses of Qt/VLC/FFmpeg/yt-dlp/zstd verified and bundled | packaging | MUST | license audit |
| REQ-REL-001 | Release gate | `WINDOWS_RELEASE_GATE.json` PASS/FAIL/BLOCKED; no false PASS | release | MUST | gate script |
| REQ-REL-002 | Reproducible | `scripts/build-windows-release.sh` reproduces build→test→stage→package→sha256 | scripts | MUST | fresh run |
| REQ-DEV-001 | Analysis first | Full system understanding before implementation (ledger, mechanics, state machines, data flow, UI bible, APIs) | research | MUST | docs present + audit |

## Hard rules

1. Never modify anything outside `win-release/` (REQ-REF-001).
2. Never re-implement yt-dlp/ffmpeg; bundle as helpers (QProcess).
3. Never introduce a second player / browser fallback for desktop playback.
4. Never claim PASS without evidence (build command, test result, real Wine run,
   real YouTube/CDN run).
5. Work feature-by-feature (analyze → port → cross-compile → wine → compare →
   next), never big-bang rewrite.
