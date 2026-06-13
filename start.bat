@echo off
title Chat-Miner Dev Server

REM Get version from config.py (single source of truth)
for /f %%i in ('python -c "from config import config; print(config.VERSION)"') do set V=%%i

echo.
echo ============================================
echo   Chat-Miner v%V% - Dev Mode
echo   Backend:  http://localhost:8857
echo   Frontend: http://localhost:5173
echo   API Docs: http://localhost:8857/docs
echo ============================================
echo.

set "ROOT=%~dp0"

echo Starting backend...
start "Chat-Miner-Backend" /d "%ROOT%" cmd /c "python -m uvicorn main:app --host 0.0.0.0 --port 8857"

echo Waiting for backend to start...
:wait_backend
timeout /t 2 /nobreak >nul
curl -s -o nul -w "%%{http_code}" http://localhost:8857/api/health 2>nul | findstr "200" >nul
if errorlevel 1 goto wait_backend

echo Backend is ready.

echo Starting frontend dev server...
start "Chat-Miner-Frontend" /d "%ROOT%frontend" cmd /c "npx vite --host 0.0.0.0 --port 5173"

echo.
echo Both servers are running. Open http://localhost:5173 in your browser.
echo Press any key to stop both servers...
pause >nul

call "%ROOT%stop.bat"
