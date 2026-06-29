#!/bin/bash

echo "=============================================================="
echo "   Tor VPN Backend Dashboard Setup (Linux)"
echo "=============================================================="
echo ""

if [ ! -f "tor/tor" ] && [ ! -f "Tor/tor" ]; then
    echo "Step 0: Downloading and extracting Tor Expert Bundle..."
    curl -sSL "https://dist.torproject.org/torbrowser/15.0.17/tor-expert-bundle-linux-x86_64-15.0.17.tar.gz" -o tor.tar.gz
    tar -xzf tor.tar.gz
    rm tor.tar.gz
    echo "[OK] Tor downloaded and extracted."
    echo ""
fi

# Check for python3
if ! command -v python3 >/dev/null 2>&1; then
    echo "[Error] python3 is not installed! Please install python3."
    exit 1
fi

echo "Step 1: Installing Python requirements..."
# Force install globally bypassing the OS protection
pip3 install -r requirements.txt --break-system-packages >/dev/null 2>&1 || pip3 install -r requirements.txt >/dev/null 2>&1 || pip install -r requirements.txt >/dev/null 2>&1
echo "[OK] Requirements installed successfully."
echo ""

if [ -f "./Tor/tor" ]; then
    chmod +x ./Tor/tor
fi
if [ -f "./tor/tor" ]; then
    chmod +x ./tor/tor
fi

echo "Step 2: Cleaning up any hanging background processes..."
pkill -f "python tor_manager.py" > /dev/null 2>&1
pkill -f "python3 tor_manager.py" > /dev/null 2>&1
pkill -x "tor" > /dev/null 2>&1
echo ""

echo "Step 3: Launching Interactive Dashboard..."
python3 tor_manager.py
