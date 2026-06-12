@echo off
cd /d "%~dp0"
echo ============================================
echo   Chat-Miner v1.0.2 Packaging Script
echo ============================================

REM Build frontend if needed
echo.
echo [0/4] Building frontend...
if not exist "frontend\dist\index.html" (
    echo   Frontend dist not found, building...
    cd frontend
    call npm run build
    if errorlevel 1 (
        echo [ERROR] Frontend build failed
        goto :error
    )
    cd ..
) else (
    echo   Frontend dist already exists, skipping.
)

REM Kill any running ChatMiner to release file locks
taskkill /f /im ChatMiner.exe >NUL 2>&1

REM Clean previous build artifacts
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

REM Build with PyInstaller
echo.
echo [1/4] Building with PyInstaller...
python -m PyInstaller --clean pyinstaller.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed
    goto :error
)

REM Copy to releases folder
echo.
echo [2/4] Copying to releases\ChatMiner...
if not exist "releases" mkdir "releases"
if exist "releases\ChatMiner" rmdir /s /q "releases\ChatMiner"
xcopy /e /i /y "dist\ChatMiner\*" "releases\ChatMiner\"
if errorlevel 1 (
    echo [ERROR] Copy to releases failed
    goto :error
)
copy /y "newbie-guide.txt" "releases\ChatMiner\" >NUL
copy /y "config.json" "releases\ChatMiner\" >NUL

REM Create portable zip
echo.
echo [3/4] Creating portable ZIP...
if exist "releases\ChatMiner-v1.0.2-portable.zip" del "releases\ChatMiner-v1.0.2-portable.zip"
powershell -Command "$ErrorActionPreference='SilentlyContinue'; Compress-Archive -Path 'releases\ChatMiner\*' -DestinationPath 'releases\ChatMiner-v1.0.2-portable.zip' -Force"
echo   ZIP created (locked-log-file warnings are harmless)

REM Build NSIS installer (auto-detect makensis)
echo.
echo [4/4] Building NSIS installer...
set MAKENSIS=
REM Use temp vars to avoid (x86) parens breaking cmd parser
set "NSIS_X86=C:\Program Files (x86)\NSIS\makensis.exe"
set "NSIS_X64=C:\Program Files\NSIS\makensis.exe"
if exist "%NSIS_X86%" set "MAKENSIS=%NSIS_X86%"
if exist "%NSIS_X64%" set "MAKENSIS=%NSIS_X64%"
where makensis >NUL 2>&1 && set MAKENSIS=makensis
if "%MAKENSIS%"=="" (
    echo [SKIP] NSIS not found. Run: makensis installer.nsi
) else (
    echo   Found: %MAKENSIS%
    "%MAKENSIS%" installer.nsi
    if errorlevel 1 (
        echo [ERROR] NSIS build failed
        goto :error
    )
    if exist "ChatMiner-v1.0.2-setup.exe" move /y "ChatMiner-v1.0.2-setup.exe" "releases\"
)

echo.
echo ============================================
echo   Build complete!
echo   Output: releases\
echo     ChatMiner\                         (portable folder)
echo     ChatMiner-v1.0.2-portable.zip      (portable zip)
if exist "releases\ChatMiner-v1.0.2-setup.exe" echo     ChatMiner-v1.0.2-setup.exe          (installer)
echo ============================================
goto :done

:error
echo.
echo ============================================
echo   BUILD FAILED! Check errors above.
echo ============================================

:done
echo.
pause
