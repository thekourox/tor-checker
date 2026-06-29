import os
import time
import signal
import threading
import logging
import requests
import stem.process
from stem.control import Controller
from stem import Signal
import shutil
import platform
import json

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("TorManager")

TEST_URL = "https://cloudflare.com/cdn-cgi/trace"
TIMEOUT = 10
LATENCY_THRESHOLD = 3.0
MAX_INSTANCES = 15

class TorInstance:
    def __init__(self, country, socks_port, control_port, data_dir, tor_cmd='tor', tor_dir=None):
        self.country = country
        self.socks_port = socks_port
        self.control_port = control_port
        self.data_dir = data_dir
        self.tor_cmd = tor_cmd
        self.tor_dir = tor_dir
        
        self.process = None
        self.active = False
        
    def start(self):
        logger.info(f"By Kourox - @kouroxdev")
        logger.info(f"[{self.country}] Starting Tor instance on SOCKS {self.socks_port}, Control {self.control_port}...")
        
        if os.path.exists(self.data_dir):
            shutil.rmtree(self.data_dir, ignore_errors=True)
        os.makedirs(self.data_dir, exist_ok=True)
        
        config = {
            'SocksPort': str(self.socks_port),
            'ControlPort': str(self.control_port),
            'CookieAuthentication': '1',
            'DataDirectory': self.data_dir.replace('\\', '/'),
            'ExitNodes': f'{{{self.country}}}',
            'StrictNodes': '1',
            'Log': 'NOTICE stdout',
            'GeoIPFile': os.path.join(os.getcwd(), 'data', 'geoip').replace('\\', '/'),
            'GeoIPv6File': os.path.join(os.getcwd(), 'data', 'geoip6').replace('\\', '/')
        }

        try:
            self.process = stem.process.launch_tor_with_config(
                config=config,
                tor_cmd=self.tor_cmd,
                take_ownership=True,
                init_msg_handler=lambda line: logger.debug(f"[{self.country}] {line}")
            )
            self.active = True
            logger.info(f"[{self.country}] Tor instance successfully started and bootstrapped.")
        except Exception as e:
            logger.error(f"[{self.country}] Failed to start Tor: {e}")
            self.active = False
            
    def request_new_ip(self):
        logger.info(f"[{self.country}] Requesting new IP (NEWNYM)...")
        try:
            with Controller.from_port(port=self.control_port) as controller:
                controller.authenticate()
                controller.signal(Signal.NEWNYM)
            logger.info(f"[{self.country}] Sent NEWNYM signal.")
            time.sleep(3)
        except Exception as e:
            logger.error(f"[{self.country}] Failed to send NEWNYM: {e}")
            
    def stop(self):
        self.active = False
        if self.process:
            logger.info(f"[{self.country}] Stopping Tor instance...")
            try:
                self.process.kill()
                self.process.wait()
            except Exception as e:
                logger.error(f"[{self.country}] Error while stopping process: {e}")
            logger.info(f"[{self.country}] Tor instance stopped.")

def get_current_ip(proxies):
    try:
        r = requests.get("https://api.ipify.org", proxies=proxies, timeout=5)
        if r.status_code == 200:
            return r.text.strip()
    except:
        pass
    return "Unknown IP"

def evaluate_proxy(instance):
    proxies = {
        'http': f'socks5h://127.0.0.1:{instance.socks_port}',
        'https': f'socks5h://127.0.0.1:{instance.socks_port}'
    }
    try:
        start_time = time.time()
        r = requests.get(TEST_URL, proxies=proxies, timeout=TIMEOUT, stream=True)
        ttfb = time.time() - start_time
        if r.status_code == 200:
            content = r.content
            total_time = time.time() - start_time
            return True, ttfb, total_time
        else:
            return False, 0, 0
    except Exception as e:
        logger.debug(f"[{instance.country}] Request failed: {e}")
        return False, 0, 0

def monitor_instance(instance):
    proxies = {
        'http': f'socks5h://127.0.0.1:{instance.socks_port}',
        'https': f'socks5h://127.0.0.1:{instance.socks_port}'
    }
    while instance.active:
        success, ttfb, total_time = evaluate_proxy(instance)
        if success:
            current_ip = get_current_ip(proxies)
            logger.info(f"[{instance.country}] Proxy on port {instance.socks_port} is healthy. IP: {current_ip}, TTFB: {ttfb:.2f}s, Total: {total_time:.2f}s")
            if total_time > LATENCY_THRESHOLD:
                logger.warning(f"[{instance.country}] Latency ({total_time:.2f}s) exceeded threshold ({LATENCY_THRESHOLD}s). Auto-healing...")
                instance.request_new_ip()
            else:
                time.sleep(15)
        else:
            logger.warning(f"[{instance.country}] Proxy connection failed or timed out. Auto-healing...")
            instance.request_new_ip()
            time.sleep(10)

instances = []

def cleanup_and_exit(signum, frame):
    logger.info("\nTermination signal received. Cleaning up...")
    for instance in instances:
        instance.stop()
        
    if platform.system() == 'Windows':
        try:
            os.system('taskkill /F /IM tor.exe >nul 2>&1')
        except:
            pass
    else:
        try:
            os.system('pkill -x tor >/dev/null 2>&1')
        except:
            pass
    os._exit(0)

def get_local_geoip_paths():
    geoip_path = os.path.join(os.getcwd(), "data", "geoip").replace('\\', '/')
    geoip6_path = os.path.join(os.getcwd(), "data", "geoip6").replace('\\', '/')
    return geoip_path, geoip6_path

def discover_exit_countries(tor_cmd):
    """
    Spawns a temporary Tor instance to read the consensus and count exit node countries.
    """
    logger.info("Starting temporary Tor process for country discovery. This may take 1-2 minutes...")
    
    geoip_path, geoip6_path = get_local_geoip_paths()
    
    discovery_data_dir = os.path.join(os.getcwd(), "tor_data", "discovery")
    if os.path.exists(discovery_data_dir):
        shutil.rmtree(discovery_data_dir, ignore_errors=True)
    os.makedirs(discovery_data_dir, exist_ok=True)
    
    config = {
        'SocksPort': 'auto',
        'ControlPort': '9049',
        'CookieAuthentication': '1',
        'DataDirectory': discovery_data_dir.replace('\\', '/'),
    }
    
    if os.path.exists(geoip_path) and os.path.exists(geoip6_path):
        logger.info(f"Local GeoIP files found. Configuring Tor to use them: {geoip_path}")
        config['GeoIPFile'] = geoip_path
        config['GeoIPv6File'] = geoip6_path
    else:
        logger.warning(f"Local GeoIP files NOT found at {geoip_path} or {geoip6_path}! Discovery will fail.")

    
    discovery_process = stem.process.launch_tor_with_config(
        config=config,
        tor_cmd=tor_cmd,
        take_ownership=True,
    )
    
    country_counts = {}
    logger.info("Tor bootstrapped. Reading network consensus...")
    
    try:
        with Controller.from_port(port=9049) as controller:
            controller.authenticate()
            statuses = controller.get_network_statuses()
            for desc in statuses:
                if 'Exit' in desc.flags and 'Valid' in desc.flags:
                    try:
                        country_code = controller.get_info(f"ip-to-country/{desc.address}")
                        if country_code and country_code != '??':
                            country_code = country_code.lower()
                            country_counts[country_code] = country_counts.get(country_code, 0) + 1
                    except Exception:
                        pass
    except Exception as e:
        logger.error(f"Discovery failed: {e}")
    finally:
        discovery_process.kill()
        discovery_process.wait()
        shutil.rmtree(discovery_data_dir, ignore_errors=True)
        
    return country_counts

def main():
    signal.signal(signal.SIGINT, cleanup_and_exit)
    signal.signal(signal.SIGTERM, cleanup_and_exit)

    base_data_dir = os.path.join(os.getcwd(), "tor_data")

    tor_cmd = "tor"
    tor_dir = None
    
    if platform.system() == 'Windows':
        possible_paths = [
            os.path.join(os.getcwd(), "Tor", "tor.exe"),
            os.path.join(os.getcwd(), "tor", "tor.exe"),
            os.path.join(os.getcwd(), "tor.exe")
        ]
    else:
        possible_paths = [
            os.path.join(os.getcwd(), "tor", "tor"),
            "/usr/bin/tor",
            "/usr/local/bin/tor"
        ]
    
    for p in possible_paths:
        if os.path.exists(p):
            tor_cmd = p
            tor_dir = os.path.dirname(p)
            break
            
    if tor_cmd == "tor":
        logger.warning("Local tor binary not found. The script will try to use 'tor' from your system PATH.")

    # 1. Discover countries
    country_counts = discover_exit_countries(tor_cmd)
    
    if not country_counts:
        logger.error("Failed to discover any exit countries. Exiting.")
        return
        
    sorted_countries = sorted(country_counts.items(), key=lambda x: x[1], reverse=True)
    top_countries = [c[0] for c in sorted_countries[:MAX_INSTANCES]]
    
    logger.info(f"Found {len(country_counts)} countries with exit nodes.")
    logger.info(f"Starting {len(top_countries)} Tor instances for the top countries: {top_countries}")

    # 2. Assign ports dynamically
    configs = []
    base_socks = 9050
    base_control = 10050
    port_mapping = {}
    
    for i, country in enumerate(top_countries):
        socks = base_socks + i
        control = base_control + i
        configs.append({"country": country, "socks_port": socks, "control_port": control})
        port_mapping[str(socks)] = country

    with open("port_mapping.json", "w") as f:
        json.dump(port_mapping, f, indent=4)
        
    logger.info(f"Generated port_mapping.json with {len(configs)} allocated ports.")

    # 3. Spawn instances
    for conf in configs:
        country = conf["country"]
        data_dir = os.path.join(base_data_dir, country)
        instance = TorInstance(
            country=country,
            socks_port=conf["socks_port"],
            control_port=conf["control_port"],
            data_dir=data_dir,
            tor_cmd=tor_cmd,
            tor_dir=tor_dir
        )
        instances.append(instance)
        instance.start()
        
    logger.info("All instances started. Beginning monitoring loops...")
    
    threads = []
    for instance in instances:
        if instance.active:
            t = threading.Thread(target=monitor_instance, args=(instance,), daemon=True)
            t.start()
            threads.append(t)
            
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup_and_exit(None, None)

if __name__ == "__main__":
    main()
