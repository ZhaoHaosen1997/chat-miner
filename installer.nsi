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
!define MUI_ICON "assets\icon.ico"
!define MUI_UNICON "assets\icon.ico"

; --- Pages ---
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"

; --- Install Section (hidden, always runs) ---
Section "主程序" SecCore
    SectionIn RO
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

    ; Refresh icon cache
    System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, i 0, i 0)'

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

; --- Desktop Shortcut ---
Section "建立桌面快捷方式" SecDesktop
    Delete "$DESKTOP\ChatMiner.lnk"
    CreateShortcut "$DESKTOP\ChatMiner.lnk" "$INSTDIR\ChatMiner.exe" \
        "" "$INSTDIR\ChatMiner.exe" 0
SectionEnd

; --- Start Menu Shortcuts ---
Section "建立开始菜单快捷方式" SecStartMenu
    Delete "$SMPROGRAMS\ChatMiner\ChatMiner.lnk"
    Delete "$SMPROGRAMS\ChatMiner\Uninstall.lnk"
    CreateDirectory "$SMPROGRAMS\ChatMiner"
    CreateShortcut "$SMPROGRAMS\ChatMiner\ChatMiner.lnk" "$INSTDIR\ChatMiner.exe" \
        "" "$INSTDIR\ChatMiner.exe" 0
    CreateShortcut "$SMPROGRAMS\ChatMiner\Uninstall.lnk" "$INSTDIR\uninstall.exe"
SectionEnd

; --- Component descriptions ---
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SecCore} "ChatMiner 核心应用程序文件。"
    !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "在桌面上创建一个快捷方式。"
    !insertmacro MUI_DESCRIPTION_TEXT ${SecStartMenu} "在开始菜单中创建快捷方式。"
!insertmacro MUI_FUNCTION_DESCRIPTION_END

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
