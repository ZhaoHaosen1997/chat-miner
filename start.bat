@echo off
chcp 65001 >nul
title Chat-Miner Dev Server

echo.
echo ============================================
echo   Chat-Miner v0.2.0 - Dev Mode
echo   Backend:  http://localhost:8856
echo   Frontend: http://localhost:5173
echo   API Docs: http://localhost:8856/docs
echo ============================================
echo.

cd /d "%~dp0"

echo Starting backend...
start "Chat-Miner-Backend" cmd /c "python -m uvicorn main:app --host 0.0.0.0 --port 8856"

echo Starting frontend dev server...
start "Chat-Miner-Frontend" cmd /c "cd frontend && npx vite --host 0.0.0.0 --port 5173"

echo.
echo Both servers are starting. Open http://localhost:5173 in your browser.
echo Press any key to stop both servers...
pause >nul

taskkill /FI "WINDOWTITLE eq Chat-Miner-Backend*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Chat-Miner-Frontend*" /T /F >nul 2>&1
echo Servers stopped.
