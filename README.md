# Tor Proxy Manager

This project provides a fully autonomous Python-based Tor Proxy Manager. It spins up multiple isolated Tor instances, binds them to specific countries (Exit Nodes), and continually monitors their latency and health. If a proxy is too slow or fails, it automatically requests a new IP to build a new circuit ("auto-healing").

## 1. Prerequisites

You will need **Python** installed on your system. If you don't have it, download and install it from [python.org](https://www.python.org/downloads/). During installation, make sure to check the box that says **"Add Python to PATH"**.

## 2. Downloading Tor (Direct Link)

Since you do not have Tor installed, follow these steps to get the exact bundle needed:

1. **Download the Windows Expert Bundle directly here:** 
   👉 [https://www.torproject.org/dist/torbrowser/13.5.3/tor-expert-bundle-windows-x86_64-13.5.3.tar.gz](https://www.torproject.org/dist/torbrowser/13.5.3/tor-expert-bundle-windows-x86_64-13.5.3.tar.gz) 
   *(Note: if that link is outdated, find the "Tor Expert Bundle" for Windows at [torproject.org/download/tor/](https://www.torproject.org/download/tor/))*
2. Open the downloaded file (you may need a tool like 7-Zip or WinRAR if Windows doesn't extract `.tar.gz` natively).
3. Inside, you will see a folder called `tor`. 
4. Extract that entire `tor` folder directly into your project folder (`c:\Users\Kourosh\Documents\tor-checker`). 
5. You should now have `c:\Users\Kourosh\Documents\tor-checker\tor\tor.exe` on your system.

## 3. Installation

Open your terminal or command prompt (cmd/PowerShell) in this project folder (`c:\Users\Kourosh\Documents\tor-checker`), and run the following command to install the required Python libraries:

```bash
pip install -r requirements.txt
```

*(This will install `stem` for controlling Tor, `requests` for making HTTP calls, and `pysocks` for SOCKS proxy support).*

## 4. Running the Manager

Once everything is set up, you can start the manager by running:

```bash
python tor_manager.py
```

### What happens when you run it?
1. The script will spawn 3 isolated Tor processes configured for the US, Germany (DE), and France (FR).
2. They will listen on SOCKS ports `9051`, `9053`, and `9055` respectively.
3. It will create an isolated data folder (`tor_data/`) for each instance to avoid conflicts.
4. It will continuously monitor the speed and latency of each proxy by downloading a small test file from Cloudflare.
5. If the latency exceeds 3 seconds or the proxy fails, it connects to the Tor Control Port and automatically requests a new IP (`NEWNYM` signal).
6. When you are done, press `Ctrl+C`. The script will gracefully shut down and run a Windows-specific command to ensure absolutely no `tor.exe` background tasks are left hanging!

## 5. Automated Testing

While the main script is running, open a **new, separate** Command Prompt or PowerShell window in the exact same folder (`c:\Users\Kourosh\Documents\tor-checker`).

Run the automated test script to instantly check your proxies:

```bash
python test_proxies.py
```

This will automatically ping through all your new proxies and output a simple result like this:
```
✅ Port 9051 -> Connected! Country: US | IP: 198.51.100.1 | Speed: 1.25 seconds
✅ Port 9053 -> Connected! Country: DE | IP: 203.0.113.5 | Speed: 0.89 seconds
❌ Port 9055 -> Failed to connect. Needs optimization.
```
