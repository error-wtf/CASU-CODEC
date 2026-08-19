; MPCASU / CASU-CODEC Windows Installer (NSIS)
; Builds a single setup.exe that installs the full MPCASU Windows package on a
; fresh Windows machine: apps, Qt runtime, libVLC, tools, pure-web + the
; embedded web-player browser. Creates Start Menu + Desktop shortcuts and an
; uninstaller. Source: the self-contained MPCASU-Windows-x86_64.zip contents.
;
; Compile (Linux):  makensis scripts/setup.nsi
; Output:           dist/MPCASU-Setup-3.0.0.exe

!include "MUI2.nsh"
!include "FileFunc.nsh"

; ------------------------------------------------------------------ metadata
!define APP_NAME "MPCASU"
!define APP_VERSION "3.0.0"
!define APP_PUBLISHER "Lino Casu / CASU-CODEC"
!define APP_EXE "MPCASU.exe"
!define OUTPUT_FILE "..\dist\MPCASU-Setup-${APP_VERSION}.exe"

Name "${APP_NAME} ${APP_VERSION}"
OutFile "${OUTPUT_FILE}"
InstallDir "$PROGRAMFILES64\MPCASU"
InstallDirRegKey HKLM "Software\MPCASU" "InstallDir"
RequestExecutionLevel admin
Unicode True
SetCompressor /SOLID lzma
; Use the CASU icon for the installer executable itself (Explorer/desktop).
Icon "..\assets\casu-installer-icon.ico"
UninstallIcon "..\assets\casu-installer-icon.ico"

; ------------------------------------------------------------- MUI settings
!define MUI_ABORTWARNING
!define MUI_ICON "..\assets\casu-installer-icon.ico"
!define MUI_UNICON "..\assets\casu-installer-icon.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "German"
!insertmacro MUI_LANGUAGE "English"

; Fixed Start Menu folder (no MUI_STARTMENUPAGE interaction; avoids the
; MUI_STARTMENU_WRITE macro variable issues on NSIS 3.x).
!define SM_FOLDER "MPCASU"

; ------------------------------------------------------------------- install
Section "Install" SecMain
  SetOutPath "$INSTDIR"

  ; The package root (unpacked from the zip) contains everything. We install
  ; the complete tree so apps find their Qt/VLC/tools/plugins/webengine deps
  ; relative to the exe, exactly like the verified package layout.
  File /r "..\dist\_stage\MPCASU-Windows-x86_64\*.*"

  ; The installer/app icon used by the shortcuts.
  File "..\assets\casu-installer-icon.ico"

  ; --- shortcuts (use the bundled CASU icon) ---
  CreateDirectory "$SMPROGRAMS\${SM_FOLDER}"
  CreateShortcut "$SMPROGRAMS\${SM_FOLDER}\MPCASU.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\casu-installer-icon.ico"
  CreateShortcut "$SMPROGRAMS\${SM_FOLDER}\CASU-Converter.lnk" "$INSTDIR\CASU-Converter.exe" "" "$INSTDIR\casu-installer-icon.ico"
  CreateShortcut "$SMPROGRAMS\${SM_FOLDER}\CASU-Web-Backend.lnk" "$INSTDIR\CASU-Web-Backend.exe" "" "$INSTDIR\casu-installer-icon.ico"
  CreateShortcut "$SMPROGRAMS\${SM_FOLDER}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\MPCASU.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\casu-installer-icon.ico"

  ; --- uninstaller ---
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MPCASU" \
    "DisplayName" "${APP_NAME} ${APP_VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MPCASU" \
    "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MPCASU" \
    "DisplayIcon" "$INSTDIR\${APP_EXE}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MPCASU" \
    "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MPCASU" \
    "Publisher" "${APP_PUBLISHER}"
  WriteRegStr HKLM "Software\MPCASU" "InstallDir" "$INSTDIR"
SectionEnd

; ---------------------------------------------------------------- uninstall
Section "Uninstall"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR"
  Delete "$SMPROGRAMS\${SM_FOLDER}\MPCASU.lnk"
  Delete "$SMPROGRAMS\${SM_FOLDER}\CASU-Converter.lnk"
  Delete "$SMPROGRAMS\${SM_FOLDER}\CASU-Web-Backend.lnk"
  Delete "$SMPROGRAMS\${SM_FOLDER}\Uninstall.lnk"
  RMDir "$SMPROGRAMS\${SM_FOLDER}"
  Delete "$DESKTOP\MPCASU.lnk"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MPCASU"
  DeleteRegKey HKLM "Software\MPCASU"
SectionEnd

; ---------------------------------------------------------- description
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain} "MPCASU Media Player + CASU tools (Qt runtime, libVLC, ffmpeg, yt-dlp, pure web) incl. embedded web-player browser."
!insertmacro MUI_FUNCTION_DESCRIPTION_END
