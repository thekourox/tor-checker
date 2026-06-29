#!/bin/bash

echo "=============================================================="
echo "   Tor VPN Backend Dashboard Setup (Linux)"
echo "=============================================================="
echo ""

echo "Step 1: Installing Python requirements..."
pip3 install -r requirements.txt >/dev/null 2>&1 || pip install -r requirements.txt >/dev/null 2>&1
echo "[OK] Requirements installed."
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

echo "Step 3: Launching Interactive Dashboard..."
python3 tor_manager.py
