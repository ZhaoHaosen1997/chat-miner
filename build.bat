@echo off
cd /d "%~dp0"

REM Get version from config.py (single source of truth)
for /f %%i in ('python -c "from config import config; print(config.VERSION)"') do set VERSION=%%i

echo ============================================
echo   Chat-Miner v%VERSION% Packaging Script
echo ============================================

REM Build frontend
echo.
echo [0/4] Building frontend...
cd frontend
call npm run build
if errorlevel 1 (
    echo [ERROR] Frontend build failed
    goto :error
)
cd ..

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
copy /y "config.json" "releases\ChatMiner\" >NUL
REM Inject version into newbie-guide
python -c "from config import config;v=config.VERSION;t=open('newbie-guide.txt',encoding='utf-8').read();open('releases/ChatMiner/newbie-guide.txt','w',encoding='utf-8').write(t.replace('{VERSION}',v))"

REM Create portable zip
echo.
echo [3/4] Creating portable ZIP...
if exist "releases\ChatMiner-v%VERSION%-portable.zip" del "releases\ChatMiner-v%VERSION%-portable.zip"
REM Wait 2s for antivirus to release file handles on fresh exe
timeout /t 2 /nobreak >NUL
powershell -Command "Compress-Archive -Path 'releases\ChatMiner\*' -DestinationPath 'releases\ChatMiner-v%VERSION%-portable.zip' -Force -ErrorAction SilentlyContinue; if (-not (Test-Path 'releases\ChatMiner-v%VERSION%-portable.zip')) { exit 1 }"
if errorlevel 1 (
    echo [ERROR] ZIP creation failed
    goto :error
)
echo   ZIP created

REM Build NSIS installer (auto-detect makensis)
echo.
echo [4/4] Building NSIS installer...
where makensis >NUL 2>&1
if errorlevel 1 (
    echo [SKIP] NSIS not found. Run: makensis installer.nsi
) else (
    echo   Found: makensis
    makensis /DVERSION=%VERSION% installer.nsi
    if errorlevel 1 (
        echo [ERROR] NSIS build failed
        goto :error
    )
)

echo.
echo ============================================
echo   Build complete!
echo   Output: releases\
echo     ChatMiner\                              (portable folder)
echo     ChatMiner-v%VERSION%-portable.zip       (portable zip)
echo     ChatMiner-v%VERSION%-setup.exe          (installer)
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
