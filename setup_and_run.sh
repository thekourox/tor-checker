#!/bin/bash

echo "=============================================================="
echo "   Tor Proxy Manager Auto-Setup (Linux)"
echo "=============================================================="
echo ""

echo "Step 1: Installing Python requirements..."
pip3 install -r requirements.txt >/dev/null 2>&1 || pip install -r requirements.txt >/dev/null 2>&1
echo "[OK] Requirements installed successfully."
echo ""

if [ -f "./Tor/tor" ]; then
    chmod +x ./Tor/tor
fi
if [ -f "./tor/tor" ]; then
    chmod +x ./tor/tor
fi

echo "Step 2: Cleaning up any hanging background processes..."
pkill -f "python3 tor_manager.py" > /dev/null 2>&1
pkill -x "tor" > /dev/null 2>&1
echo ""

echo "Step 3: Starting Tor Manager in the background..."
rm -f port_mapping.json
nohup python3 tor_manager.py > manager_logs.txt 2>&1 &
MANAGER_PID=$!
echo "[OK] Tor Manager started."
echo ""

echo "Step 4: Scanning global network for all countries... This can take 1-2 minutes!"
while [ ! -f port_mapping.json ]; do
    sleep 5
done
echo "[OK] Countries successfully discovered and ports are mapped!"
echo "Waiting an additional 15 seconds for the proxies to finish connecting..."
sleep 15
echo ""

echo "=============================================================="
echo "   Final Connection Status Report:"
echo "=============================================================="
python3 test_proxies.py | tee test_logs.txt

echo ""
echo "=============================================================="
echo "Setup complete!"
echo "The program is running in the background. You can safely close this terminal."
echo "To stop the Tor Manager, run this command:"
echo "kill $MANAGER_PID"
echo "=============================================================="
