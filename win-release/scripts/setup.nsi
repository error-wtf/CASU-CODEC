; MPCASU / CASU-CODEC Windows Installer (NSIS)
; Builds a single setup.exe that installs the full MPCASU Windows package on a
; fresh Windows machine: apps, Qt runtime, libVLC, tools, pure-web + the
; embedded web-player browser (WebView2). Creates Start Menu + Desktop
; shortcuts (per-app icons) and an uninstaller. Source: the self-contained
; MPCASU-Windows-x86_64.zip contents.
;
; Upgrade behavior: an existing installation (machine OR per-user) is detected
; via the registry and updated IN PLACE — running apps are closed first, files
; are overwritten, shortcuts/registry refreshed. No second copy is created.
;
; Privilege model: RequestExecutionLevel highest — NO forced UAC prompt.
;   - Elevated (admin) launch  -> machine install: $PROGRAMFILES64\MPCASU,
;     HKLM registry, system PATH (like the previous releases).
;   - Normal (non-admin) launch -> per-user install: $LOCALAPPDATA\MPCASU,
;     HKCU registry, user PATH. A non-writable old machine install cannot be
;     updated without rights; the installer then falls back to a fresh
;     per-user copy instead of failing.
;
; Compile (Linux):  makensis scripts/setup.nsi
; Output:           dist/MPCASU-Setup-7.0.0.exe

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "WinMessages.nsh"
; UserInfo plugin (GetAccountType) is used without its optional .nsh header.

; ------------------------------------------------------------------ metadata
!define APP_NAME "MPCASU"
!define APP_VERSION "7.0.0"
!define APP_PUBLISHER "Lino Casu / CASU-CODEC"
!define APP_EXE "MPCASU.exe"
!define OUTPUT_FILE "..\dist\MPCASU-Setup-${APP_VERSION}.exe"

Name "${APP_NAME} ${APP_VERSION}"
OutFile "${OUTPUT_FILE}"
InstallDir "$PROGRAMFILES64\MPCASU"
RequestExecutionLevel highest
Unicode True
SetCompressor zlib
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

; ------------------------------------------------------------- global state
; $AdminMode   1 = elevated/machine-wide, 0 = per-user
Var AdminMode

; ------------------------------------------------------------------- .onInit
Function .onInit
  ; --- detect privileges (no UAC prompt; highest available token wins) -----
  UserInfo::GetAccountType
  Pop $0
  StrCmp $0 "Admin" admin_mode
  StrCmp $0 "Power" admin_mode
  StrCpy $AdminMode 0
  Goto pick_dir
admin_mode:
  StrCpy $AdminMode 1

pick_dir:
  ; --- auto-update: reuse the previous installation directory --------------
  ; Machine install first (legacy releases wrote here), then per-user.
  ReadRegStr $INSTDIR HKLM "Software\MPCASU" "InstallDir"
  IfErrors no_machine_key 0
  Push $INSTDIR
  Call DirWritable
  Pop $0
  StrCmp $0 1 done_dir no_machine_key
no_machine_key:
  ClearErrors
  ReadRegStr $INSTDIR HKCU "Software\MPCASU" "InstallDir"
  IfErrors no_user_key 0
  Goto done_dir
no_user_key:
  ClearErrors
  StrCpy $INSTDIR "$PROGRAMFILES64\MPCASU"
  ; Non-admin without any previous install -> default to a per-user location.
  StrCmp $AdminMode 1 done_dir
  StrCpy $INSTDIR "$LOCALAPPDATA\MPCASU"
done_dir:
  ClearErrors
FunctionEnd

; DirWritable: Push <dir>; Call DirWritable; Pop <0|1>
; Creates a probe subdirectory to test actual write access.
Function DirWritable
  Exch $0
  Push $1
  StrCpy $1 "$0\__casu_write_probe"
  RMDir "$1"
  CreateDirectory "$1"
  IfFileExists "$1" 0 not_writable
  RMDir "$1"
  StrCpy $0 1
  Goto finish
not_writable:
  StrCpy $0 0
finish:
  Pop $1
  Exch $0
FunctionEnd

; ------------------------------------------------------------ PATH helpers
; Appends $INSTDIR to the PATH of the current privilege scope (system PATH in
; HKLM when elevated, user PATH in HKCU otherwise) once, and broadcasts the
; change to running processes. Registers `casu`/`casu-converter`/
; `CASU-Web-Backend` callable from any shell, exactly like /usr/bin on Linux.
; NOTE: NSIS requires literal registry roots, hence the explicit branches.
Function AddToSystemPath
  StrCmp $AdminMode 1 read_machine_path
  ReadRegStr $0 HKCU "Environment" "Path"
  Goto path_read
read_machine_path:
  ReadRegStr $0 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "Path"
path_read:
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
    StrCmp $AdminMode 1 write_machine_path
    WriteRegExpandStr HKCU "Environment" "Path" "$0"
    Goto done
  write_machine_path:
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

; RemoveFromSystemPath: removes $INSTDIR from the PATH of the current scope.
Function RemoveFromSystemPath
  StrCmp $AdminMode 1 read_machine_path
  ReadRegStr $0 HKCU "Environment" "Path"
  Goto path_read
read_machine_path:
  ReadRegStr $0 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "Path"
path_read:
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
    StrCmp $AdminMode 1 write_machine_path
    WriteRegExpandStr HKCU "Environment" "Path" "$0"
    Goto done
  write_machine_path:
    WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "Path" "$0"
  done:
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
; from the PATH, preserving all other entries. Simple, robust: rebuild the
; PATH segment-by-segment. Verified under Wine (does NOT empty PATH).
; Stack parameter: "machine" (HKLM system PATH) or "user" (HKCU user PATH).
Function un.RemoveFromSystemPath
  Exch $9
  StrCmp $9 "machine" 0 read_user
  ReadRegStr $0 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "Path"
  Goto segloop
read_user:
  ReadRegStr $0 HKCU "Environment" "Path"
segloop:
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
    StrCmp $9 "machine" 0 write_user
    WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "Path" "$1"
    Goto broadcast
  write_user:
    WriteRegExpandStr HKCU "Environment" "Path" "$1"
broadcast:
  SendMessage ${HWND_BROADCAST} ${WM_SETTINGCHANGE} 0 "STR:Environment" /TIMEOUT=5000
  Pop $9
FunctionEnd

; CloseRunningApps: terminate any running CASU apps so an in-place upgrade can
; overwrite the binaries ("Update" must never fail due to locked files).
Function CloseRunningApps
  nsExec::ExecToLog 'taskkill /IM MPCASU.exe /F'
  Pop $0
  nsExec::ExecToLog 'taskkill /IM CASU-Converter.exe /F'
  Pop $0
  nsExec::ExecToLog 'taskkill /IM CASU-Web-Backend.exe /F'
  Pop $0
  Sleep 400
FunctionEnd

; un.CloseRunningApps: same, for the uninstaller.
Function un.CloseRunningApps
  nsExec::ExecToLog 'taskkill /IM MPCASU.exe /F'
  Pop $0
  nsExec::ExecToLog 'taskkill /IM CASU-Converter.exe /F'
  Pop $0
  nsExec::ExecToLog 'taskkill /IM CASU-Web-Backend.exe /F'
  Pop $0
  Sleep 400
FunctionEnd

; ------------------------------------------------------------------- install
Section "Install" SecMain
  SetOutPath "$INSTDIR"

  ; Stop running instances before overwriting (auto-update requirement).
  Call CloseRunningApps

  ; The package root (unpacked from the zip) contains everything. We install
  ; the complete tree so apps find their Qt/VLC/tools/webview2 deps relative
  ; to the exe, exactly like the verified package layout.
  File /r "..\dist\_stage\MPCASU-Windows-x86_64\*.*"

  ; Official Evergreen runtime installs in-place; WebView2 stays inside MPCASU.
  DetailPrint "Installing Microsoft Edge WebView2 Runtime (Internet required if missing)..."
  ExecWait '"$INSTDIR\tools\MicrosoftEdgeWebview2Setup.exe" /silent /install' $0
  ${If} $0 != 0
    DetailPrint "WebView2 setup returned $0. An existing runtime may already be installed."
  ${EndIf}

  ; --- per-app shortcuts (each app shows its OWN icon, mirroring the Linux
  ;     desktop entries: mpcasu-player / casu-converter / web-casu) ---
  CreateDirectory "$SMPROGRAMS\${SM_FOLDER}"
  CreateShortcut "$SMPROGRAMS\${SM_FOLDER}\MPCASU.lnk" \
    "$INSTDIR\${APP_EXE}" "" "$INSTDIR\assets\mpcasu_player_icon.ico"
  CreateShortcut "$SMPROGRAMS\${SM_FOLDER}\CASU-Converter.lnk" \
    "$INSTDIR\CASU-Converter.exe" "" "$INSTDIR\assets\casu_converter_icon.ico"
  CreateShortcut "$SMPROGRAMS\${SM_FOLDER}\CASU-Web-Backend.lnk" \
    "$INSTDIR\CASU-Web-Backend.exe" "" "$INSTDIR\assets\web_casu_icon.ico"
  CreateShortcut "$SMPROGRAMS\${SM_FOLDER}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\MPCASU.lnk" \
    "$INSTDIR\${APP_EXE}" "" "$INSTDIR\assets\mpcasu_player_icon.ico"

  ; --- uninstaller + registration (per-machine or per-user scope) ---
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  StrCmp $AdminMode 1 reg_machine
  ; ---- per-user (HKCU) registration ----
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MPCASU" \
    "DisplayName" "${APP_NAME} ${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MPCASU" \
    "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MPCASU" \
    "DisplayIcon" "$INSTDIR\${APP_EXE}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MPCASU" \
    "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MPCASU" \
    "Publisher" "${APP_PUBLISHER}"
  WriteRegStr HKCU "Software\MPCASU" "InstallDir" "$INSTDIR"
  Goto registration_done
reg_machine:
  ; ---- per-machine (HKLM) registration ----
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
registration_done:

  ; --- system-wide/per-user registration (exact Linux parity: casu on PATH +
  ;     file types) ---
  Call AddToSystemPath

  ; --- file-type associations (.casu, .mp5 -> MPCASU); NSIS needs literal
  ;     roots, so both scopes are written explicitly ---
  StrCmp $AdminMode 1 classes_machine
  WriteRegStr HKCU "Software\Classes\.casu" "" "MPCASU.Container"
  WriteRegStr HKCU "Software\Classes\.mp5" "" "MPCASU.Container"
  WriteRegStr HKCU "Software\Classes\MPCASU.Container" "" "CASU container"
  WriteRegStr HKCU "Software\Classes\MPCASU.Container\DefaultIcon" "" \
    '"$INSTDIR\assets\mpcasu_player_icon.ico"'
  WriteRegStr HKCU "Software\Classes\MPCASU.Container\shell\open\command" "" \
    '"$INSTDIR\${APP_EXE}" "%1"'
  WriteRegStr HKCU "Software\Classes\MPCASU.Container\shell\open" "" "&Play in MPCASU"
  Goto classes_done
classes_machine:
  WriteRegStr HKLM "Software\Classes\.casu" "" "MPCASU.Container"
  WriteRegStr HKLM "Software\Classes\.mp5" "" "MPCASU.Container"
  WriteRegStr HKLM "Software\Classes\MPCASU.Container" "" "CASU container"
  WriteRegStr HKLM "Software\Classes\MPCASU.Container\DefaultIcon" "" \
    '"$INSTDIR\assets\mpcasu_player_icon.ico"'
  WriteRegStr HKLM "Software\Classes\MPCASU.Container\shell\open\command" "" \
    '"$INSTDIR\${APP_EXE}" "%1"'
  WriteRegStr HKLM "Software\Classes\MPCASU.Container\shell\open" "" "&Play in MPCASU"
classes_done:
SectionEnd

; ---------------------------------------------------------------- uninstall
Section "Uninstall"
  ; stop running instances so files are not locked
  Call un.CloseRunningApps
  ; remove PATH entries + file-type associations from BOTH scopes (a per-user
  ; uninstall must not leave a stale machine registration and vice versa).
  Push "machine"
  Call un.RemoveFromSystemPath
  Push "user"
  Call un.RemoveFromSystemPath

  DeleteRegKey HKLM "Software\Classes\.casu"
  DeleteRegKey HKLM "Software\Classes\.mp5"
  DeleteRegKey HKLM "Software\Classes\MPCASU.Container"
  DeleteRegKey HKCU "Software\Classes\.casu"
  DeleteRegKey HKCU "Software\Classes\.mp5"
  DeleteRegKey HKCU "Software\Classes\MPCASU.Container"

  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR"
  Delete "$SMPROGRAMS\${SM_FOLDER}\MPCASU.lnk"
  Delete "$SMPROGRAMS\${SM_FOLDER}\CASU-Converter.lnk"
  Delete "$SMPROGRAMS\${SM_FOLDER}\CASU-Web-Backend.lnk"
  Delete "$SMPROGRAMS\${SM_FOLDER}\Uninstall.lnk"
  RMDir "$SMPROGRAMS\${SM_FOLDER}"
  Delete "$DESKTOP\MPCASU.lnk"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\MPCASU"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MPCASU"
  DeleteRegKey HKLM "Software\MPCASU"
  DeleteRegKey HKCU "Software\MPCASU"
SectionEnd

; ---------------------------------------------------------- description
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain} "MPCASU Media Player + CASU tools (Qt runtime, libVLC, ffmpeg, yt-dlp, pure web) incl. embedded web-player browser (WebView2). Updates an existing installation automatically."
!insertmacro MUI_FUNCTION_DESCRIPTION_END
