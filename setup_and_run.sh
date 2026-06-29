#!/bin/bash

echo "=============================================================="
echo "   Tor VPN Backend Dashboard Setup (Linux)"
echo "=============================================================="
echo ""

if ! python3 -m venv --help > /dev/null 2>&1; then
    echo "[!] Virtual environment module not found. Installing python3-venv..."
    sudo apt-get update && sudo apt-get install -y python3-venv python3-pip
fi

echo "Step 1: Setting up Python Virtual Environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate

echo ""
echo "Step 2: Installing Python requirements..."
pip install -r requirements.txt >/dev/null 2>&1
echo "[OK] Requirements installed."
echo ""

if [ -f "./Tor/tor" ]; then
    chmod +x ./Tor/tor
fi
if [ -f "./tor/tor" ]; then
    chmod +x ./tor/tor
fi

echo "Step 3: Cleaning up any hanging background processes..."
pkill -f "python tor_manager.py" > /dev/null 2>&1
pkill -x "tor" > /dev/null 2>&1
echo ""

echo "Step 4: Launching Interactive Dashboard..."
python tor_manager.py
