#!/bin/bash

echo "=============================================================="
echo "   Tor VPN Backend Dashboard Setup (Linux)"
echo "=============================================================="
echo ""

# Check for python3
if ! command -v python3 >/dev/null 2>&1; then
    echo "[Error] python3 is not installed! Please install python3."
    exit 1
fi

# Ensure python3-venv is available
if ! python3 -m venv --help > /dev/null 2>&1; then
    echo "[!] python3-venv module not found. Attempting to install it..."
    if [ "$EUID" -ne 0 ]; then
        sudo apt-get update && sudo apt-get install -y python3-venv python3-pip
    else
        apt-get update && apt-get install -y python3-venv python3-pip
    fi
    
    # Check again if it succeeded
    if ! python3 -m venv --help > /dev/null 2>&1; then
        echo "[Error] Failed to install python3-venv. Please run: apt-get install python3-venv"
        exit 1
    fi
fi

echo "Step 1: Setting up Python Virtual Environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv || { echo "[Error] Failed to create virtual environment"; exit 1; }
fi
source venv/bin/activate || { echo "[Error] Failed to activate virtual environment"; exit 1; }

echo ""
echo "Step 2: Installing Python requirements..."
pip3 install -r requirements.txt || { echo "[Error] Failed to install requirements!"; exit 1; }
echo "[OK] Requirements installed successfully."
echo ""

if [ -f "./Tor/tor" ]; then
    chmod +x ./Tor/tor
fi
if [ -f "./tor/tor" ]; then
    chmod +x ./tor/tor
fi

echo "Step 3: Cleaning up any hanging background processes..."
pkill -f "python tor_manager.py" > /dev/null 2>&1
pkill -f "python3 tor_manager.py" > /dev/null 2>&1
pkill -x "tor" > /dev/null 2>&1
echo ""

echo "Step 4: Launching Interactive Dashboard..."
python3 tor_manager.py
