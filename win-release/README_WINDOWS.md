# MPCASU / CASU-CODEC — Windows Port (win-release)

Target: **C++20 + Qt 6 + CMake + Ninja + MinGW-w64**, Windows x86_64,
cross-compiled under Linux, verified under Wine.

This directory is the **only write area** of the frozen repository. The rest
of `/home/error/Codec-Casu` is the read-only reference (specification, test
oracle, design reference).

## Status

- Baseline frozen: `WINDOWS_PORT_BASELINE.md` (HEAD `36df249`, 400 tests PASS)
- Pure Web Release 2.0.0 published (SHA256 in baseline)
- Phase: **READ-ONLY analysis** (research/ + roadmap/ documents)
- Tool inventory + feature matrix created
- Implementation: **not started yet** (analysis-first per requirements)

## Planned deliverables

```
dist/MPCASU-Windows-x86_64.zip
    MPCASU.exe
    CASU-Converter.exe
    CASU-Web-Backend.exe
    Qt6*.dll
    plugins/platforms/qwindows.dll
    vlc/ (libvlc.dll + plugins)
    tools/ (ffmpeg.exe, ffprobe.exe, yt-dlp.exe)
    web/pure/  (byte-identical Pure Web Release)
    LICENSE, THIRD_PARTY_LICENSES/, README_WINDOWS.md
```

## Toolchain (to install)

- `mingw-w64` (`x86_64-w64-mingw32-g++`)
- `cmake`, `ninja`
- Qt 6 cross toolchain (or Qt 6 binaries for MinGW)
- `wine` / `wine64`

## Working method

1. Read reference code thoroughly (read-only).
2. Analyze → port one module → cross-compile → unit test → Wine test →
   compare to reference → mark VERIFIED → next module.
3. Never modify anything outside `win-release/`.
4. Never claim PASS without runtime evidence.
