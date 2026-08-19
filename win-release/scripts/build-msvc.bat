@echo off
REM ============================================================================
REM  build-msvc.bat — build MPCASU + CASU apps on native Windows with the MSVC
REM  toolchain and QtWebEngine (exact embedded-browser parity with Linux).
REM
REM  This produces the EXACT same apps as the Linux release, with the embedded
REM  Chromium (QtWebEngine) for the web-provider tabs (Spotify/Hearthis/Tidal/
REM  Netflix/BROWSE). YouTube stays on the yt-dlp -> loopback -> libVLC pipeline
REM  (no browser tab), exactly like Linux.
REM
REM  Prerequisites on the Windows build machine:
REM    - Visual Studio 2022 with "Desktop development with C++" (MSVC x64)
REM    - CMake >= 3.21 and Ninja
REM    - Python 3 (only used here to fetch Qt via aqtinstall)
REM    - Git (optional)
REM
REM  Qt 6.8.3 (MSVC x64) incl. QtWebEngine is downloaded automatically via
REM  aqtinstall into %USERPROFILE%\Qt if QT6_MSVC_DIR is not already set.
REM ============================================================================
setlocal enabledelayedexpansion

set "BUILD_DIR=build-msvc"
set "GENERATOR=Ninja"

REM ---- 1. Locate the MSVC environment (via vswhere or the VS install) ----
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" set "VSWHERE=%ProgramFiles%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" (
    echo [ERROR] Visual Studio Installer vswhere.exe not found. Install VS2022.
    exit /b 1
)
for /f "usebackq tokens=*" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSINSTALL=%%i"
if not defined VSINSTALL (
    echo [ERROR] No Visual Studio with C++ x64 tools found.
    exit /b 1
)
call "%VSINSTALL%\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 (
    echo [ERROR] vcvars64.bat failed.
    exit /b 1
)

REM ---- 2. Ensure Qt 6.8.3 MSVC x64 with QtWebEngine ----
if not defined QT6_MSVC_DIR (
    set "QT6_MSVC_DIR=%USERPROFILE%\Qt\6.8.3\msvc2022_64"
    if not exist "%QT6_MSVC_DIR%" (
        echo [1/5] Installing Qt 6.8.3 MSVC x64 + QtWebEngine via aqtinstall...
        pip install --user aqtinstall
        aqt install-qt windows desktop 6.8.3 win64_msvc2022_64 -m qtwebengine -O "%USERPROFILE%\Qt"
        if errorlevel 1 (
            echo [ERROR] Qt install failed.
            exit /b 1
        )
    )
)
echo [2/5] Qt at: %QT6_MSVC_DIR%

REM ---- 3. Configure with MSVC + QtWebEngine ----
echo [3/5] Configuring (QtWebEngine enabled)...
cmake -S . -B "%BUILD_DIR%" -G "%GENERATOR%" ^
      -DCMAKE_BUILD_TYPE=Release ^
      -DCMAKE_PREFIX_PATH="%QT6_MSVC_DIR%"
if errorlevel 1 exit /b 1

REM ---- 4. Build ----
echo [4/5] Building...
cmake --build "%BUILD_DIR%" --config Release
if errorlevel 1 exit /b 1

REM ---- 5. Test (native Windows) ----
echo [5/5] Running tests...
ctest --test-dir "%BUILD_DIR%" -C Release --output-on-failure
if errorlevel 1 exit /b 1

echo.
echo ============================================================================
echo  BUILD OK — MPCASU with QtWebEngine (embedded web-player tabs)
echo  Executables in %BUILD_DIR%\apps\mpcasu\Release\MPCASU.exe
echo ============================================================================
endlocal