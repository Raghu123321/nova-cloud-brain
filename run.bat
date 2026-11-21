@echo off
title NOVA Cloud Brain Server (MaaS)
color 0b

echo ======================================================================
echo                  NOVA CLOUD BRAIN (MaaS v3.0)
echo ======================================================================
echo.
echo [*] Project Location: %~dp0
echo [*] Starting Uvicorn API Server on port 8000...
echo.
echo [*] Web Console:    http://localhost:8000
echo [*] API Docs:       http://localhost:8000/docs
echo [*] Admin Login:    Username: admin  ^|  Password: admin123
echo.
echo ======================================================================
echo.

cd /d "%~dp0"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Server encountered an error or was stopped.
    pause
)
