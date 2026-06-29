@echo off
echo ==============================================================
echo   Tor VPN Backend Dashboard Setup (Windows)
echo ==============================================================
echo.
echo Step 1: Setting up Python Virtual Environment...
if not exist venv (
    python -m venv venv
)
call venv\Scripts\activate.bat

echo.
echo Step 2: Installing Python requirements...
pip install -r requirements.txt >nul 2>&1
echo [OK] Requirements installed.
echo.

echo Step 3: Cleaning up any hanging Tor processes...
taskkill /F /IM tor.exe >nul 2>&1
echo.

echo Step 4: Launching Interactive Dashboard...
python tor_manager.py

pause
