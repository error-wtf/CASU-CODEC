#!/usr/bin/env bash
# dll-audit.sh — DLL/binary audit (WP-REL-004).
#   dll-audit.sh [exe...]
# For each Windows exe: prints PE info, the imported DLL names, and flags any
# imported DLL that is NOT bundled in the packaged zip (dev-PATH dependence =
# packaging FAIL). Use after `cpack` has produced dist/MPCASU-Windows-x86_64.zip.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

ZIP="${ZIP:-dist/_stage/MPCASU-Windows-x86_64.zip}"
[ -f "$ZIP" ] || ZIP="$(ls -1 dist/MPCASU-Windows-x86_64.zip 2>/dev/null | head -1)"
if [[ -z "$ZIP" || ! -f "$ZIP" ]]; then
    echo "dll-audit: package zip not found (run build-windows-release.sh first)" >&2
    exit 2
fi

declare -a EXES=("$@")
if [[ ${#EXES[@]} -eq 0 ]]; then
    EXES=(
        build-win64/src/hello/casu_hello.exe
        build-win64/tests/casu_core_test.exe
        build-win64/apps/casu-cli/casu.exe
    )
fi

# DLLs shipped inside the package (lower-cased, basename only).
BUNDLED="$(unzip -l "$ZIP" | grep -oE '[A-Za-z0-9_.-]+\.dll' \
           | tr '[:upper:]' '[:lower:]' | sort -u)"

KNOWN_SYS_DLLS="kernel32.dll user32.dll advapi32.dll shell32.dll ole32.dll oleaut32.dll \
gdi32.dll comdlg32.dll ws2_32.dll wsock32.dll winmm.dll msvcrt.dll msvcp60.dll \
ucrtbase.dll api-ms-win-crt-*.dll shlwapi.dll version.dll setupapi.dll wtsapi32.dll \
dwmapi.dll imm32.dll uxtheme.dll dxgi.dll d3d11.dll d3d9.dll ddraw.dll opengl32.dll \
libgcc_s_seh-1.dll libstdc++-6.dll libwinpthread-1.dll"

fail=0
for exe in "${EXES[@]}"; do
    echo "=== $exe ==="
    file "$exe" | sed 's/^/    file: /'
    echo "    imported DLLs:"
    while read -r dll; do
        [ -z "$dll" ] && continue
        dl="$(tr '[:upper:]' '[:lower:]' <<<"$dll")"
        sys=0; for s in $KNOWN_SYS_DLLS; do [[ "$dl" == $s ]] && sys=1; done
        if grep -qxF "$dl" <<<"$BUNDLED" || [[ "$sys" == "1" ]]; then
            echo "      OK   $dll"
        else
            echo "      MISS $dll  (not in package, not a known system DLL)"
            fail=1
        fi
    done < <(x86_64-w64-mingw32-objdump -p "$exe" | sed -n 's/^[[:space:]]*DLL Name:[[:space:]]*//p' | sort -u)
done

if [[ "$fail" == "1" ]]; then
    echo "dll-audit: FAIL — some imported DLLs are not self-contained" >&2
    exit 1
fi
echo "dll-audit: OK — all imported DLLs are system or bundled"
