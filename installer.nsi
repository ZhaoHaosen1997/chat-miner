; Chat-Miner Installer
; NSIS 3.x script - generates setup.exe
;
; Build: makensis /DVERSION=x.y.z installer.nsi
; Note: build.bat auto-passes /DVERSION from config.py

!ifndef VERSION
  !define VERSION "0.0.0"
!endif

!include "MUI2.nsh"
!include "FileFunc.nsh"

; --- General ---
Name "ChatMiner"
OutFile "releases\ChatMiner-v${VERSION}-setup.exe"
InstallDir "$LOCALAPPDATA\ChatMiner"
RequestExecutionLevel user
SetCompressor /SOLID lzma

; --- Interface ---
!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"

; --- Pages ---
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"

; --- Install Section ---
Section "Install"
    ; Kill running ChatMiner to release file locks before overwrite
    nsExec::Exec 'taskkill /f /im ChatMiner.exe'
    Sleep 1500
    SetOutPath "$INSTDIR"

    ; Main program files (always overwrite)
    SetOverwrite on
    File /r /x config.json "releases\ChatMiner\*.*"

    ; config.json: preserve existing user config, do not overwrite
    SetOverwrite off
    File "releases\ChatMiner\config.json"
    SetOverwrite on

    CreateDirectory "$INSTDIR\data"
    WriteUninstaller "$INSTDIR\uninstall.exe"

    ; Start Menu
    CreateDirectory "$SMPROGRAMS\ChatMiner"
    CreateShortcut "$SMPROGRAMS\ChatMiner\ChatMiner.lnk" "$INSTDIR\ChatMiner.exe"
    CreateShortcut "$SMPROGRAMS\ChatMiner\Uninstall.lnk" "$INSTDIR\uninstall.exe"

    ; Desktop
    CreateShortcut "$DESKTOP\ChatMiner.lnk" "$INSTDIR\ChatMiner.exe"

    ; Registry (uninstall info)
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatMiner" \
        "DisplayName" "ChatMiner"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatMiner" \
        "UninstallString" "$INSTDIR\uninstall.exe"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatMiner" \
        "DisplayVersion" "${VERSION}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatMiner" \
        "Publisher" "ChatMiner"
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatMiner" \
        "NoModify" 1
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatMiner" \
        "NoRepair" 1

    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatMiner" \
        "EstimatedSize" "$0"
SectionEnd

; --- Uninstall Section ---
Section "Uninstall"
    Delete "$DESKTOP\ChatMiner.lnk"
    RMDir /r "$SMPROGRAMS\ChatMiner"

    MessageBox MB_YESNO|MB_ICONQUESTION \
        "Delete all data (chat records, database, logs)?$\n$\nChoose 'No' to keep your data." \
        IDYES delete_data IDNO keep_data

    delete_data:
        RMDir /r "$INSTDIR"
        Goto done

    keep_data:
        Delete "$INSTDIR\ChatMiner.exe"
        Delete "$INSTDIR\uninstall.exe"
        RMDir /r "$INSTDIR\_internal"
        Goto done

    done:
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatMiner"
SectionEnd
