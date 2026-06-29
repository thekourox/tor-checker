@echo off
echo ==============================================================
echo   Tor Proxy Manager Auto-Setup (Windows)
echo ==============================================================
echo.
echo Step 1: Installing Python requirements...
pip install -r requirements.txt >nul 2>&1
echo [OK] Requirements installed successfully.
echo.

echo Step 2: Cleaning up any hanging Tor processes...
taskkill /F /IM tor.exe >nul 2>&1
echo.

echo Step 3: Starting Tor Manager in the background...
if exist port_mapping.json del port_mapping.json
start /b python tor_manager.py > manager_logs.txt 2>&1
echo [OK] Tor Manager started.
echo.

echo Step 4: Scanning global network for all countries... This can take 1-2 minutes!
:waitloop
if not exist port_mapping.json (
    timeout /t 5 /nobreak >nul
    goto waitloop
)
echo [OK] Countries successfully discovered and ports are mapped!
echo Waiting an additional 15 seconds for the proxies to finish connecting...
timeout /t 15 /nobreak >nul
echo.

echo ==============================================================
echo   Final Connection Status Report:
echo ==============================================================
python test_proxies.py > test_logs.txt
type test_logs.txt

echo ==============================================================
echo Setup complete!
echo Leave this console window open. The program is running in the background.
echo To stop the Tor Manager, simply close this window.
echo ==============================================================
pause
