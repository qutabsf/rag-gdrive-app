@echo off
title RAG Knowledge Base - Setup
color 0A

echo.
echo  ==========================================
echo   RAG Knowledge Base - First-Time Setup
echo  ==========================================
echo.

:: ── Check Python ───────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    color 0C
    echo  ERROR: Python is not installed.
    echo.
    echo  Please do the following:
    echo    1. Go to https://www.python.org/downloads/
    echo    2. Click "Download Python" (the big yellow button)
    echo    3. Run the installer
    echo    4. IMPORTANT: Check the box "Add Python to PATH"
    echo    5. Re-run this installer after Python is installed.
    echo.
    pause
    exit /b 1
)

echo  [OK] Python is installed.
echo.

:: ── Install dependencies ────────────────────────────────────────────────────
echo  Installing required libraries (this may take 2-5 minutes)...
echo  Please wait - do not close this window.
echo.

pip install -r requirements.txt >install_log.txt 2>&1
if errorlevel 1 (
    color 0C
    echo  ERROR: Failed to install libraries.
    echo  See install_log.txt for details.
    pause
    exit /b 1
)

echo  [OK] Libraries installed.
echo.

:: ── Create .env if missing ──────────────────────────────────────────────────
if not exist .env (
    copy .env.example .env >nul
    echo  [OK] Created configuration file (.env)
) else (
    echo  [OK] Configuration file already exists.
)

echo.
echo  ==========================================
echo   Setup Complete!
echo  ==========================================
echo.
echo  NEXT STEPS:
echo.
echo  1. Get your FREE Anthropic API key:
echo     - Go to https://console.anthropic.com
echo     - Sign up or log in
echo     - Click "API Keys" then "Create Key"
echo     - Copy the key (starts with sk-ant-...)
echo.
echo  2. Set up Google Drive access:
echo     (The app will guide you through this)
echo.
echo  3. Double-click "run.bat" to start the app.
echo.
pause
