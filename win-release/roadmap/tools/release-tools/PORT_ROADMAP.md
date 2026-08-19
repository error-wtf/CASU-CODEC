# Release / Packaging Tools — Windows Port Roadmap (TOOL-RELEASE)

Reference: `packaging/build_debs.sh`, `tools/release_gate_guard.py`,
`dist/SHA256SUMS`. Windows replaces the deb pipeline with a reproducible
`build-windows-release.sh` (CMake/CPack + Wine + packaging + gate).

## WP-REL-001 cmake/mingw64-toolchain.cmake
- PURPOSE: x86_64-w64-mingw32 toolchain, C++20, warnings, Debug/Release/
  RelWithDebInfo. Gate: hello-Windows-exe builds (PE32+) + runs under Wine.
- STATUS: NOT_STARTED.

## WP-REL-002 Top-level CMake (modular targets) + deps + packaging.cmake
- Targets: casu_core, casu_codec, casu_media, casu_network, casu_playback,
  casu_webapi, mpcasu, casu_converter, casu_web_backend, casu_cli.
- CPack zip layout: exes, Qt DLLs, plugins/platforms/qwindows.dll,
  vlc/ (libvlc.dll + plugins), tools/ (ffmpeg.exe/ffprobe.exe/yt-dlp.exe),
  web/pure/ + web/backend assets, LICENSE, THIRD_PARTY_LICENSES/,
  README_WINDOWS.md. STATUS: NOT_STARTED.

## WP-REL-003 scripts/build-windows-release.sh (reproducible)
- 1 configure → 2 build → 3 unit → 4 wine → 5 stage → 6 package → 7 sha256 →
  8 gate. Fresh run reproducible. STATUS: NOT_STARTED.

## WP-REL-004 DLL/binary audit
- `file`, `x86_64-w64-mingw32-objdump -p` on each exe; detect missing DLLs;
  no dependence on dev PATH. STATUS: NOT_STARTED.

## WP-REL-005 Clean-Wine-prefix package test
- New empty WINEPREFIX; only the packaged zip contents (no dev DLLs/PATH).
  If it only runs in dev prefix → FAIL. STATUS: VERIFIED (2026-08-18).
  In neuem `WINEPREFIX` nur mit Paketinhalt: `MPCASU.exe --smoke` +
  `CASU-Converter.exe --smoke-test` + `casu.exe kind/verify/mp5-info` +
  `CASU-Web-Backend.exe` (web/, /api/version, web/pure/index.html) OK.
  Marker: `test-results/clean-prefix.log` = `CLEAN_PREFIX_PASS`.

## WP-REL-006 WINDOWS_RELEASE_GATE.json
- Machine-readable PASS/FAIL/BLOCKED/NOT_TESTED for: build, unit_tests,
  compatibility, codec, converter, player, youtube, network, web_backend,
  pure_web, packaging, wine, licenses. BLOCKED > false PASS. STATUS: VERIFIED
  (2026-08-18). `scripts/release_gate.sh` → `dist/WINDOWS_RELEASE_GATE.json`;
  alle 13 Gates PASS beim finalen Build.

## WP-REL-007 Licenses audit
- Adopt THIRD_PARTY_LICENSES/README policy; copy exact license texts for
  bundled Qt/libVLC/FFmpeg/zstd/yt-dlp/MinGW-runtime/SQLite; record versions
  + hashes; source offers. CASU license unchanged. STATUS: VERIFIED
  (2026-08-18; ergänzt um OpenSSL 3.4.1 Apache-2.0 + Hash).

## WP-REL-008 SHA256 + reproducibility verification
- Fresh build-windows-release.sh run produces identical package+hashes.
- STATUS: VERIFIED (2026-08-18). Zwei getrennte cpack-Läufe → 513 Dateien
  byte-identisch (`diff -rq` leer); nur Zip-Container-Timestamps unterscheiden
  sich (CPack mtime). `dist/SHA256SUMS` geschrieben.
