@echo off
chcp 65001 >nul
title Stop Chat-Miner Servers

echo Stopping Chat-Miner servers...

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8856"') do (
    taskkill /F /PID %%a >nul 2>&1
)

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8857"') do (
    taskkill /F /PID %%a >nul 2>&1
)

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173"') do (
    taskkill /F /PID %%a >nul 2>&1
)

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5174"') do (
    taskkill /F /PID %%a >nul 2>&1
)

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5175"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo Done. All Chat-Miner servers stopped.
timeout /t 2 >nul
