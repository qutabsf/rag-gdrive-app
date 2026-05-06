@echo off
title RAG Knowledge Base

:: Ensure Python Scripts are on PATH
set "PATH=%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%LOCALAPPDATA%\Programs\Python\Python311;%PATH%"

:: Skip Streamlit email prompt
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
    mkdir "%USERPROFILE%\.streamlit" 2>nul
    echo [general] > "%USERPROFILE%\.streamlit\credentials.toml"
    echo email = "" >> "%USERPROFILE%\.streamlit\credentials.toml"
)

:: Open browser after short delay
start "" /b cmd /c "timeout /t 5 >nul && start http://localhost:8501"

:: Start the app
streamlit run "%~dp0app.py"

pause
