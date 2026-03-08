@echo off
echo Starting Roblox Outfit Studio...
cd /d "%~dp0"
python src\main.py
if errorlevel 1 (
    echo.
    echo ERROR: Failed to start. Make sure dependencies are installed:
    echo   pip install -r requirements.txt
    pause
)
