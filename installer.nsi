; Chat-Miner Installer
; NSIS 3.x script

!ifndef VERSION
  !define VERSION "0.0.0"
!endif

!include "MUI2.nsh"
!include "FileFunc.nsh"

Name "ChatMiner"
OutFile "releases\ChatMiner-v${VERSION}-setup.exe"
InstallDir "$LOCALAPPDATA\ChatMiner"
RequestExecutionLevel user
SetCompressor /SOLID lzma

Var IsUpgrade
Var OldVersion

Function .onInit
    ClearErrors
    ReadRegStr $OldVersion HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatMiner" "DisplayVersion"
    ${If} $OldVersion != ""
        StrCpy $IsUpgrade "1"
        ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatMiner" "UninstallString"
        ${If} $0 != ""
            ${GetParent} "$0" $0
            StrCpy $INSTDIR "$0"
        ${EndIf}
    ${Else}
        StrCpy $IsUpgrade "0"
    ${EndIf}
FunctionEnd

!define MUI_ABORTWARNING
!define MUI_ICON "assets\icon.ico"
!define MUI_UNICON "assets\icon.ico"

!define MUI_WELCOMEPAGE_TITLE "ChatMiner v${VERSION}"
!define MUI_WELCOMEPAGE_TEXT "ChatMiner - 微信/QQ 群聊分析工具$\r$\n$\r$\nAI 生成每日报告、群友画像、事件时间轴、年度颁奖典礼。$\r$\n$\r$\n点击下一步继续。"

!define MUI_FINISHPAGE_RUN "$INSTDIR\ChatMiner.exe"
!define MUI_FINISHPAGE_RUN_TEXT "立即启动 ChatMiner"

!insertmacro MUI_PAGE_WELCOME
Page custom UpgradePage_Show
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"

Function UpgradePage_Show
    ${If} $IsUpgrade == "1"
        MessageBox MB_OKCANCEL|MB_ICONINFORMATION \
            "检测到已安装 ChatMiner v$OldVersion。$\r$\n$\r$\n将升级到 v${VERSION}，数据和设置将被保留。$\r$\n$\r$\n点击确定继续升级。" \
            IDOK go_upgrade
        Quit
        go_upgrade:
        Abort
    ${EndIf}
FunctionEnd

Section "主程序" SecCore
    SectionIn RO
    nsExec::Exec 'taskkill /f /im ChatMiner.exe'
    Sleep 1500
    SetOutPath "$INSTDIR"
    SetOverwrite on
    File /r /x config.json "releases\ChatMiner\*.*"
    SetOverwrite off
    File "releases\ChatMiner\config.json"
    SetOverwrite on
    CreateDirectory "$INSTDIR\data"
    WriteUninstaller "$INSTDIR\uninstall.exe"
    System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, i 0, i 0)'
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatMiner" "DisplayName" "ChatMiner"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatMiner" "UninstallString" "$INSTDIR\uninstall.exe"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatMiner" "DisplayVersion" "${VERSION}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatMiner" "Publisher" "ChatMiner"
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatMiner" "NoModify" 1
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatMiner" "NoRepair" 1
    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatMiner" "EstimatedSize" "$0"
SectionEnd

Section "桌面快捷方式" SecDesktop
    Delete "$DESKTOP\ChatMiner.lnk"
    CreateShortcut "$DESKTOP\ChatMiner.lnk" "$INSTDIR\ChatMiner.exe" "" "$INSTDIR\ChatMiner.exe" 0
SectionEnd

Section "开始菜单快捷方式" SecStartMenu
    Delete "$SMPROGRAMS\ChatMiner\ChatMiner.lnk"
    Delete "$SMPROGRAMS\ChatMiner\Uninstall.lnk"
    CreateDirectory "$SMPROGRAMS\ChatMiner"
    CreateShortcut "$SMPROGRAMS\ChatMiner\ChatMiner.lnk" "$INSTDIR\ChatMiner.exe" "" "$INSTDIR\ChatMiner.exe" 0
    CreateShortcut "$SMPROGRAMS\ChatMiner\Uninstall.lnk" "$INSTDIR\uninstall.exe"
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SecCore} "ChatMiner 主应用程序文件。"
    !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "在桌面上创建快捷方式。"
    !insertmacro MUI_DESCRIPTION_TEXT ${SecStartMenu} "在开始菜单中创建快捷方式。"
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Section "Uninstall"
    Delete "$DESKTOP\ChatMiner.lnk"
    RMDir /r "$SMPROGRAMS\ChatMiner"
    MessageBox MB_YESNO|MB_ICONQUESTION \
        "是否同时删除所有群聊数据？$\r$\n$\r$\n选【是】将删除聊天记录、数据库、日志等。$\r$\n$\r$\n选【否】仅卸载程序，保留数据（下次安装可继续使用）。" \
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
