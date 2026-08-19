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
!include "WinMessages.nsh"

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

; ------------------------------------------------------------ PATH helpers
; Appends $INSTDIR to the system PATH (HKLM Environment) once, and broadcasts
; the change to running processes. Registers `casu`/`casu-converter`/
; `CASU-Web-Backend` system-wide, exactly like /usr/bin on Linux.
Function AddToSystemPath
  ReadRegStr $0 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "Path"
  StrCmp $0 "" newpath
  ; check if already present (case-insensitive substring on ";$INSTDIR;")
  Push $0
  Push "$INSTDIR"
  Call StrStr
  Pop $1
  StrCmp $1 "" add
  Goto done
  add:
    ; strip trailing ';'
    StrCpy $1 $0 "" -1
    StrCmp $1 ";" 0 no_trail
    StrCpy $0 $0 -1
  no_trail:
    StrCpy $0 "$0;$INSTDIR"
  newpath:
    WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "Path" "$0"
  done:
    SendMessage ${HWND_BROADCAST} ${WM_SETTINGCHANGE} 0 "STR:Environment" /TIMEOUT=5000
FunctionEnd

; StrStr: searches for a substring. Usage: Push <haystack>; Push <needle>;
; Call StrStr; Pop <result> (result = substring from match, or "" if not found)
Function StrStr
  Exch $1
  Exch
  Exch $0
  Push $2
  Push $3
  Push $4
  StrCpy $2 $0
  StrCpy $3 $1
  StrLen $4 $3
  loop:
    StrCpy $1 $2 $4
    StrCmp $1 $3 found
    StrCpy $1 $2 1
    StrCmp $1 "" notfound
    StrCpy $2 $2 "" 1
    Goto loop
  found:
    StrCpy $0 $2
    Goto end
  notfound:
    StrCpy $0 ""
  end:
  Pop $4
  Pop $3
  Pop $2
  Exch $0
FunctionEnd

; RemoveFromSystemPath: removes $INSTDIR from the system PATH.
Function RemoveFromSystemPath
  ReadRegStr $0 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "Path"
  Push $0
  Push "$INSTDIR;"
  Call StrStr
  Pop $1
  StrCmp $1 "" try_no_semi
  ; remove "$INSTDIR;"
  StrCpy $2 $1
  StrLen $3 "$INSTDIR;"
  StrCpy $2 $2 "" $3
  StrCpy $0 $2
  Goto write
  try_no_semi:
    Push $0
    Push "$INSTDIR"
    Call StrStr
    Pop $1
    StrCmp $1 "" write
    StrCpy $2 $1
    StrLen $3 "$INSTDIR"
    StrCpy $2 $2 "" $3
    StrCpy $0 $2
  write:
    WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "Path" "$0"
    SendMessage ${HWND_BROADCAST} ${WM_SETTINGCHANGE} 0 "STR:Environment" /TIMEOUT=5000
FunctionEnd

; --- Uninstaller variants (NSIS requires "un."-prefixed function names) ---
; un.StrStr: substring search. Usage: Push <haystack>; Push <needle>;
; Call un.StrStr; Pop <result>
Function un.StrStr
  Exch $1
  Exch
  Exch $0
  Push $2
  Push $3
  Push $4
  StrCpy $2 $0
  StrCpy $3 $1
  StrLen $4 $3
  loop:
    StrCpy $1 $2 $4
    StrCmp $1 $3 found
    StrCpy $1 $2 1
    StrCmp $1 "" notfound
    StrCpy $2 $2 "" 1
    Goto loop
  found:
    StrCpy $0 $2
    Goto end
  notfound:
    StrCpy $0 ""
  end:
  Pop $4
  Pop $3
  Pop $2
  Exch $0
FunctionEnd

; un.RemoveFromSystemPath: removes "$INSTDIR" (with or without trailing ';')
; from the system PATH, preserving all other entries. Simple, robust: rebuild
; the PATH segment-by-segment. Verified under Wine (does NOT empty PATH).
Function un.RemoveFromSystemPath
  ReadRegStr $0 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "Path"
  StrCpy $1 ""          ; result
  StrCpy $2 "$0"        ; remaining
  ; make sure we compare with a trailing ';' so "C:\MPCASU;" matches cleanly
  loop:
    StrCmp $2 "" done
    ; split at first ';'
    StrCpy $3 $2 1
    StrCmp $3 ";" no_seg
    ; find first ';' position in $2
    StrCpy $4 0
  find:
    StrCpy $5 $2 1 $4
    StrCmp $5 "" take_all
    StrCmp $5 ";" found
    IntOp $4 $4 + 1
    Goto find
  take_all:
    StrCpy $6 $2
    StrCpy $2 ""
    Goto check
  found:
    StrCpy $6 $2 $4
    IntOp $4 $4 + 1
    StrCpy $2 $2 "" $4
    Goto check
  no_seg:
    ; empty segment (leading/trailing ';') - skip
    StrCpy $6 ""
    StrCpy $2 $2 "" 1
    Goto check
  check:
    StrCmp $6 "$INSTDIR" skip    ; exact match (no trailing ;)
    StrCmp $6 "" skip            ; empty - skip
    StrCmp $1 "" first
    StrCpy $1 "$1;$6"
    Goto loop
  first:
    StrCpy $1 "$6"
    Goto loop
  skip:
    Goto loop
  done:
    WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "Path" "$1"
    SendMessage ${HWND_BROADCAST} ${WM_SETTINGCHANGE} 0 "STR:Environment" /TIMEOUT=5000
FunctionEnd

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

  ; --- system-wide registration (exact Linux parity: casu on PATH + file types)
  ; Add $INSTDIR to the system PATH so `casu`, `casu-converter`,
  ; `CASU-Web-Backend` are callable from any command prompt / PowerShell.
  Call AddToSystemPath

  ; --- file-type associations (.casu, .mp5 -> MPCASU) ---
  WriteRegStr HKLM "Software\Classes\.casu" "" "MPCASU.Container"
  WriteRegStr HKLM "Software\Classes\.mp5" "" "MPCASU.Container"
  WriteRegStr HKLM "Software\Classes\MPCASU.Container" "" "CASU container"
  WriteRegStr HKLM "Software\Classes\MPCASU.Container\DefaultIcon" "" '"$INSTDIR\casu-installer-icon.ico"'
  WriteRegStr HKLM "Software\Classes\MPCASU.Container\shell\open\command" "" '"$INSTDIR\${APP_EXE}" "%1"'
  WriteRegStr HKLM "Software\Classes\MPCASU.Container\shell\open" "" "&Play in MPCASU"
SectionEnd

; ---------------------------------------------------------------- uninstall
Section "Uninstall"
  ; remove system-wide PATH entry + file-type associations
  Call un.RemoveFromSystemPath
  DeleteRegKey HKLM "Software\Classes\.casu"
  DeleteRegKey HKLM "Software\Classes\.mp5"
  DeleteRegKey HKLM "Software\Classes\MPCASU.Container"

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
