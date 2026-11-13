@echo off
cd /d "%~dp0"
python miditema.py %*
if errorlevel 1 (
    echo.
    echo [!] miditema termino con un error.
    pause
)
