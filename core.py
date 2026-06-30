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
import re
import psutil
import psutil
import random
import socket
import socks
import atexit

socket.setdefaulttimeout(20)

# Setup File Logging ONLY (No console spam)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("manager_logs.txt", mode='w', encoding='utf-8')]
)
logger = logging.getLogger("TorManager")

TEST_URL = "https://1.1.1.1/cdn-cgi/trace"
SPEED_TEST_URL = "https://speed.cloudflare.com/__down?bytes=100000" # 100KB payload
TIMEOUT = 15
LATENCY_THRESHOLD = 8.0
SPEED_THRESHOLD_KBS = 5.0
PORT_LOCK = threading.Lock()
NEXT_SOCKS_PORT = 9050
NEXT_CONTROL_PORT = 10050
G_STANDBY_POOL = []
G_COUNTRY_FINGERPRINTS = {}
G_TOR_CMD = "tor"

COUNTRY_PORTS_FILE = "country_ports.json"

def get_port_for_country(country_code):
    mapping = {}
    if os.path.exists(COUNTRY_PORTS_FILE):
        try:
            with open(COUNTRY_PORTS_FILE, "r") as f:
                mapping = json.load(f)
        except:
            pass
            
    if country_code in mapping:
        return mapping[country_code]['socks'], mapping[country_code]['control']
        
    used_socks = [v['socks'] for v in mapping.values()]
    used_control = [v['control'] for v in mapping.values()]
    
    new_socks = max(used_socks) + 1 if used_socks else 9050
    new_control = max(used_control) + 1 if used_control else 10050
    
    while new_socks in used_socks:
        new_socks += 1
    while new_control in used_control:
        new_control += 1
        
    mapping[country_code] = {'socks': new_socks, 'control': new_control}
    
    try:
        with open(COUNTRY_PORTS_FILE, "w") as f:
            json.dump(mapping, f, indent=4)
    except:
        pass
        
    return new_socks, new_control

def spawn_country(country_code):
    global instances
    
    socks_port, control_port = get_port_for_country(country_code)
    
    data_dir = os.path.join(os.getcwd(), 'tor_data', f'data_{country_code}')
    fps = G_COUNTRY_FINGERPRINTS.get(country_code, [])
    
    instance = TorInstance(country_code, socks_port, control_port, data_dir, G_TOR_CMD, fps)
    
    with QUEUE_LOCK:
        instances.append(instance)
        
    threading.Thread(target=instance.start, daemon=True).start()
    time.sleep(1) # Staggered Bootstrapping delay

def detect_hardware_tier():
    try:
        ram_gb = psutil.virtual_memory().total / (1024**3)
        cores = psutil.cpu_count(logical=True) or 2
    except:
        ram_gb = 4.0
        cores = 2
        
    tier = 'HIGH'
    if ram_gb < 6.0 or cores <= 2:
        tier = 'LOW'
    elif ram_gb < 12.0 or cores <= 4:
        tier = 'MID'
        
    return tier, cores, ram_gb

HARDWARE_TIER, CPU_CORES, RAM_GB = detect_hardware_tier()

# Global state for the API
dashboard_state = {
    'status': 'stopped', # stopped, discovering, spawning, running
    'phase': 'idle',
    'discovery_msg': 'Ready to start.',
    'discovery_progress': 0,
    'instances': {}
}

# Admin Configs
CONFIG_PING_INTERVAL = 30
CONFIG_RAM_LIMIT_MB = 15
CONFIG_BW_LIMIT_KB = 0

QUEUE_LOCK = threading.Lock()

class TorInstance:
    def __init__(self, country, socks_port, control_port, data_dir, tor_cmd, available_fingerprints):
        self.country = country
        self.socks_port = socks_port
        self.control_port = control_port
        self.data_dir = data_dir
        self.tor_cmd = tor_cmd
        self.available_fingerprints = available_fingerprints
        self.fingerprint_index = 0
        
        self.process = None
        self.active = False
        
        # Scheduler fields
        self.next_check_time = time.time() + 15  # Give it 15s to bootstrap initially
        self.currently_checking = False
        self.consecutive_failures = 0

        
        # Init dashboard state
        dashboard_state['instances'][self.country] = {
            'port': str(self.socks_port),
            'ip_location': '...',
            'ping': '...',
            'status': '🟡 Bootstrapping...'
        }
        
    def start(self):
        logger.info(f"[{self.country}] Starting Tor instance on SOCKS {self.socks_port}, Control {self.control_port}...")
        
        if os.path.exists(self.data_dir):
            shutil.rmtree(self.data_dir, ignore_errors=True)
        os.makedirs(self.data_dir, exist_ok=True)
        
        discovery_data_dir = os.path.join(os.getcwd(), "tor_data", "discovery")
        if os.path.exists(discovery_data_dir):
            for filename in os.listdir(discovery_data_dir):
                if filename.startswith("cached-"):
                    src = os.path.join(discovery_data_dir, filename)
                    dst = os.path.join(self.data_dir, filename)
                    try:
                        if os.path.isfile(src):
                            shutil.copy2(src, dst)
                    except Exception:
                        pass
        
        bind_ip = '0.0.0.0' if platform.system() == 'Linux' else '127.0.0.1'
        config = {
            'SocksPort': f'{bind_ip}:{self.socks_port}',
            'ControlPort': f'127.0.0.1:{self.control_port}',
            'CookieAuthentication': '1',
            'DataDirectory': self.data_dir.replace('\\', '/'),
            'StrictNodes': '1',
            'Log': 'NOTICE stdout',
            'GeoIPFile': os.path.join(os.getcwd(), 'data', 'geoip').replace('\\', '/'),
            'GeoIPv6File': os.path.join(os.getcwd(), 'data', 'geoip6').replace('\\', '/'),
            'ClientUseIPv6': '0',
            'ClientPreferIPv6ORPort': '0',
            'EnforceDistinctSubnets': '0',
            'ConnectionPadding': '0',
            'ReducedConnectionPadding': '1',
            'EntryNodes': '{nl},{de},{fr},{gb},{us},{ca}',
            'KeepalivePeriod': '120',
            'CircuitStreamTimeout': '15',
            'ClientOnly': '1',
            'FetchDirInfoEarly': '0',
            'FetchDirInfoExtraEarly': '0',
            'FetchUselessDescriptors': '0'
        }
        
        config['MaxMemInQueues'] = f'{CONFIG_RAM_LIMIT_MB} MB'
        if CONFIG_BW_LIMIT_KB > 0:
            config['BandwidthRate'] = f'{CONFIG_BW_LIMIT_KB} KBytes'
            config['BandwidthBurst'] = f'{CONFIG_BW_LIMIT_KB * 2} KBytes'
            
        # Extreme Resource Minimization for all tiers
        config['NumCPUs'] = '1'
        config['AvoidDiskWrites'] = '1'
        
        if self.available_fingerprints:
            best_fingerprint = self.available_fingerprints[0]
            self.fingerprint_index = 1
            config['ExitNodes'] = f'${best_fingerprint}'
            logger.info(f"[{self.country}] Using optimal starting fingerprint: {best_fingerprint}")
        else:
            config['ExitNodes'] = f'{{{self.country}}}'

        def handle_init_msg(line):
            match = re.search(r'Bootstrapped (\d+)%', line)
            if match:
                dashboard_state['instances'][self.country]['status'] = f"🟡 Bootstrapping {match.group(1)}%"
            logger.info(f"[{self.country}] {line}")

        try:
            self.process = stem.process.launch_tor_with_config(
                config=config,
                tor_cmd=self.tor_cmd,
                take_ownership=False,
                init_msg_handler=handle_init_msg,
                timeout=None
            )
            self.active = True
            dashboard_state['instances'][self.country]['status'] = "🟢 Online. Testing..."
            logger.info(f"[{self.country}] Tor instance successfully started and bootstrapped.")

            def drain_stdout(stream):
                try:
                    for _ in stream:
                        pass
                except:
                    pass
            if self.process and self.process.stdout:
                threading.Thread(target=drain_stdout, args=(self.process.stdout,), daemon=True).start()
        except Exception as e:
            logger.error(f"[{self.country}] Failed to start Tor: {e}")
            err_msg = str(e).split('\\n')[0][:30]
            dashboard_state['instances'][self.country]['status'] = f"🔴 {err_msg}"
            self.active = False
            
    def request_new_ip(self, reason):
        logger.info(f"[{self.country}] Requesting new IP. Reason: {reason}")
        
        if self.fingerprint_index < len(self.available_fingerprints):
            best_fingerprint = self.available_fingerprints[self.fingerprint_index]
            self.fingerprint_index += 1
            dashboard_state['instances'][self.country]['status'] = f"🟡 Optimizing ({best_fingerprint[:8]})..."
            logger.info(f"[{self.country}] Auto-healing using specific high-bandwidth fingerprint: {best_fingerprint}")
            try:
                with Controller.from_port(address='127.0.0.1', port=self.control_port) as controller:
                    controller.authenticate()
                    controller.set_conf('ExitNodes', f'${best_fingerprint}')
                    controller.signal(Signal.NEWNYM)
                time.sleep(3)
            except Exception as e:
                logger.error(f"[{self.country}] Failed to SETCONF: {e}")
                err_msg = str(e).split('\\n')[0][:30]
                dashboard_state['instances'][self.country]['status'] = f"🔴 Opt Fail: {err_msg}"
        else:
            dashboard_state['instances'][self.country]['status'] = "🟡 Auto-Healing (Random)..."
            try:
                with Controller.from_port(address='127.0.0.1', port=self.control_port) as controller:
                    controller.authenticate()
                    controller.set_conf('ExitNodes', f'{{{self.country}}}')
                    controller.signal(Signal.NEWNYM)
                time.sleep(3)
            except Exception as e:
                logger.error(f"[{self.country}] Failed to send NEWNYM: {e}")
                err_msg = str(e).split('\\n')[0][:30]
                dashboard_state['instances'][self.country]['status'] = f"🔴 Opt Fail: {err_msg}"
            
    def stop(self):
        self.active = False
        
        # Free Python HTTP Session Memory
        if getattr(self, 'session', None):
            try:
                self.session.close()
                self.session = None
            except:
                pass
                
        if self.process:
            logger.info(f"[{self.country}] Stopping Tor instance...")
            try:
                self.process.kill()
                self.process.wait()
            except Exception as e:
                logger.error(f"[{self.country}] Error while stopping process: {e}")
            logger.info(f"[{self.country}] Tor instance stopped.")

def measure_ping(instance):
    ping_ms = 0
    success = False
    actual_country = None
    
    try:
        s = socks.socksocket()
        s.set_proxy(socks.SOCKS5, "127.0.0.1", instance.socks_port)
        s.settimeout(10.0)
        
        ping_start = time.time()
        s.connect(("8.8.8.8", 443))
        ping_end = time.time()
        s.close()
        
        ping_ms = int((ping_end - ping_start) * 1000)
        success = True
    except Exception as e:
        success = False
        
    if success:
        try:
            proxies = {
                'http': f'socks5h://127.0.0.1:{instance.socks_port}',
                'https': f'socks5h://127.0.0.1:{instance.socks_port}'
            }
            if getattr(instance, 'session', None) is None:
                instance.session = requests.Session()
                
            resp = instance.session.get('https://1.1.1.1/cdn-cgi/trace', proxies=proxies, timeout=10)
            if resp.status_code == 200:
                for line in resp.text.splitlines():
                    if line.startswith('loc='):
                        actual_country = line.split('=')[1].upper()
                        break
                        
            if not actual_country or actual_country in ['T1', 'XX', 'A1']:
                ip_resp = instance.session.get('https://ipinfo.io/country', proxies=proxies, timeout=10)
                if ip_resp.status_code == 200:
                    actual_country = ip_resp.text.strip().upper()
        except:
            pass
            
    return success, ping_ms, actual_country

def scheduler_worker(worker_id):
    logger.info(f"Worker {worker_id} started.")
    while dashboard_state['status'] == 'running':
        now = time.time()
        instance_to_check = None
        
        with QUEUE_LOCK:
            for inst in instances:
                # Pick up active instances, OR sleeping instances that are ready to wake up
                if not inst.currently_checking and now >= inst.next_check_time:
                    if inst.active or (not inst.active and inst.consecutive_failures >= 3):
                        instance_to_check = inst
                        inst.currently_checking = True
                        break
                    elif not inst.active and inst.consecutive_failures == 0:
                        # Failed to even start initially? Let's just retry it.
                        instance_to_check = inst
                        inst.currently_checking = True
                        break
                        
        if not instance_to_check:
            time.sleep(1)
            continue
            
        if not instance_to_check.active:
            # Waking up from sleep!
            logger.info(f"[{instance_to_check.country}] Waking up from sleep mode...")
            instance_to_check.consecutive_failures = 0
            instance_to_check.fingerprint_index = 0
            instance_to_check.start()
            instance_to_check.currently_checking = False
            continue
        try:
            success, ping_ms, actual_country = measure_ping(instance_to_check)
            
            with QUEUE_LOCK:
                if success:
                    instance_to_check.consecutive_failures = 0
                    
                    actual_country_str = actual_country if actual_country else instance_to_check.country.upper()
                    dashboard_state['instances'][instance_to_check.country]['ip_location'] = actual_country_str
                    
                    if actual_country and actual_country.lower() != instance_to_check.country.lower():
                        logger.warning(f"[{instance_to_check.country}] Mismatched Country! Expected {instance_to_check.country}, got {actual_country}.")
                        
                        instance_to_check.consecutive_failures += 1
                        if instance_to_check.consecutive_failures >= 3:
                            dashboard_state['instances'][instance_to_check.country]['status'] = f"💤 Sleeping (5m) [Bad Country: {actual_country}]"
                            instance_to_check.stop()
                            instance_to_check.next_check_time = time.time() + 300
                        else:
                            dashboard_state['instances'][instance_to_check.country]['status'] = f"🔴 Wrong Country ({actual_country})"
                            threading.Thread(target=instance_to_check.request_new_ip, args=(f"Wrong Country ({actual_country})",), daemon=True).start()
                            instance_to_check.next_check_time = time.time() + 10
                            
                        instance_to_check.currently_checking = False
                        continue
                        
                    dashboard_state['instances'][instance_to_check.country]['ping'] = f"{ping_ms} ms"
                    dashboard_state['instances'][instance_to_check.country]['status'] = "🟢 Online"
                    
                    if ping_ms > (LATENCY_THRESHOLD * 1000):
                        instance_to_check.request_new_ip(f"High Ping ({ping_ms}ms)")
                        instance_to_check.next_check_time = time.time() + 10
                    else:
                        instance_to_check.next_check_time = time.time() + CONFIG_PING_INTERVAL
                else:
                    instance_to_check.consecutive_failures += 1
                    dashboard_state['instances'][instance_to_check.country]['ping'] = "Timeout"
                    
                    if instance_to_check.consecutive_failures >= 3:
                        dashboard_state['instances'][instance_to_check.country]['status'] = f"💤 Sleeping (5m) [Network Timeout]"
                        instance_to_check.stop()
                        instance_to_check.next_check_time = time.time() + 300
                    else:
                        dashboard_state['instances'][instance_to_check.country]['status'] = f"🟡 Timeout. Retrying..."
                        threading.Thread(target=instance_to_check.request_new_ip, args=(f"Ping Timeout",), daemon=True).start()
                        instance_to_check.next_check_time = time.time() + 10

                    instance_to_check.next_check_time = time.time() + 10
        except Exception as e:
            logger.error(f"Worker {worker_id} error: {e}")
        finally:
            instance_to_check.currently_checking = False

instances = []
global_thread = None

def stop_all():
    dashboard_state['status'] = 'stopped'
    dashboard_state['phase'] = 'idle'
    dashboard_state['discovery_msg'] = 'Network stopped.'
    for instance in instances:
        instance.stop()
    instances.clear()
    
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

def discover_exit_countries(tor_cmd):
    dashboard_state['phase'] = 'discovery'
    dashboard_state['discovery_msg'] = "Starting local Tor discovery process..."
    
    geoip_path = os.path.join(os.getcwd(), "data", "geoip").replace('\\\\', '/')
    geoip6_path = os.path.join(os.getcwd(), "data", "geoip6").replace('\\\\', '/')
    
    discovery_data_dir = os.path.join(os.getcwd(), "tor_data", "discovery")
    if os.path.exists(discovery_data_dir):
        shutil.rmtree(discovery_data_dir, ignore_errors=True)
    os.makedirs(discovery_data_dir, exist_ok=True)
    
    config = {
        'SocksPort': '127.0.0.1:auto',
        'ControlPort': '127.0.0.1:9049',
        'CookieAuthentication': '1',
        'DataDirectory': discovery_data_dir.replace('\\\\', '/'),
        'ClientUseIPv6': '0',
        'ClientPreferIPv6ORPort': '0'
    }
    
    if os.path.exists(geoip_path) and os.path.exists(geoip6_path):
        config['GeoIPFile'] = geoip_path
        config['GeoIPv6File'] = geoip6_path

    def handle_init_msg(line):
        match = re.search(r'Bootstrapped (\d+)%', line)
        if match:
            dashboard_state['discovery_progress'] = int(match.group(1))
            dashboard_state['discovery_msg'] = f"Bootstrapping Discovery Node: {match.group(1)}%"

    try:
        discovery_process = stem.process.launch_tor_with_config(
            config=config,
            tor_cmd=tor_cmd,
            take_ownership=False,
            init_msg_handler=handle_init_msg,
            timeout=None
        )
    except Exception as e:
        error_msg = f"Error launching Tor ({tor_cmd}): {str(e)}"
        logger.error(error_msg)
        dashboard_state['discovery_msg'] = error_msg
        return {}, {}
    
    country_fingerprints = {}
    country_counts = {}
    
    dashboard_state['discovery_msg'] = "Node Bootstrapped. Parsing Global Network Consensus..."
    
    try:
        with Controller.from_port(address='127.0.0.1', port=9049) as controller:
            controller.authenticate()
            statuses = controller.get_network_statuses()
            for desc in statuses:
                if 'Exit' in desc.flags and 'Valid' in desc.flags:
                    try:
                        country_code = controller.get_info(f"ip-to-country/{desc.address}")
                        if country_code and country_code != '??':
                            country_code = country_code.lower()
                            
                            bw = desc.bandwidth if desc.bandwidth else 0
                            if country_code not in country_fingerprints:
                                country_fingerprints[country_code] = []
                            country_fingerprints[country_code].append((desc.fingerprint, bw))
                            country_counts[country_code] = country_counts.get(country_code, 0) + 1
                    except Exception:
                        pass
                        
            for c in country_fingerprints:
                country_fingerprints[c].sort(key=lambda x: x[1], reverse=True)
                country_fingerprints[c] = [x[0] for x in country_fingerprints[c]]
                
    except Exception as e:
        logger.error(f"Discovery failed: {e}")
    finally:
        discovery_process.kill()
        discovery_process.wait()
        
    return country_counts, country_fingerprints

def start_network_thread(max_instances, ping_interval, ram_limit_mb, bandwidth_limit_kb, worker_count, selected_countries):
    global global_thread, G_STANDBY_POOL
    global CONFIG_PING_INTERVAL, CONFIG_RAM_LIMIT_MB, CONFIG_BW_LIMIT_KB
    
    CONFIG_PING_INTERVAL = ping_interval
    CONFIG_RAM_LIMIT_MB = ram_limit_mb
    CONFIG_BW_LIMIT_KB = bandwidth_limit_kb
    
    dashboard_state['status'] = 'discovering'
    
    if HARDWARE_TIER == 'LOW':
        threading.stack_size(262144)
    elif HARDWARE_TIER == 'MID':
        threading.stack_size(524288)
        
    tor_cmd = "tor"
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
            break

    try:
        country_counts, country_fingerprints = discover_exit_countries(tor_cmd)
        if not country_counts:
            dashboard_state['status'] = 'stopped'
            if not dashboard_state['discovery_msg'].startswith('Error'):
                dashboard_state['discovery_msg'] = 'Discovery failed. No exit nodes found.'
            return
    except Exception as e:
        dashboard_state['status'] = 'stopped'
        dashboard_state['discovery_msg'] = f"Fatal Error: {str(e)}"
        return
        
    sorted_countries = sorted(country_counts.items(), key=lambda x: x[1], reverse=True)
    all_available_countries = [c[0] for c in sorted_countries]
    
    active_countries = []
    
    if selected_countries:
        preferred = [c.strip().lower() for c in selected_countries.split(",") if c.strip()]
        for p in preferred:
            if p in all_available_countries and p not in active_countries:
                active_countries.append(p)
                if len(active_countries) >= max_instances:
                    break
            elif p not in all_available_countries:
                # Add to dashboard as unsupported
                dashboard_state['instances'][p.lower()] = {
                    'socks_port': 'N/A',
                    'ip_location': 'N/A',
                    'ping': '...',
                    'status': '🔴 Unsupported (No Tor Relays)'
                }
                    
    # Then fill the rest
    for c in all_available_countries:
        if len(active_countries) >= max_instances:
            break
        if c not in active_countries:
            active_countries.append(c)
            
    global NEXT_SOCKS_PORT, NEXT_CONTROL_PORT, G_COUNTRY_FINGERPRINTS, G_TOR_CMD
    G_STANDBY_POOL = [c for c in all_available_countries if c not in active_countries]
    G_COUNTRY_FINGERPRINTS = country_fingerprints
    G_TOR_CMD = tor_cmd
    NEXT_SOCKS_PORT = 9050
    NEXT_CONTROL_PORT = 10050

    if os.path.exists("port_mapping.json"):
        try:
            os.remove("port_mapping.json")
        except:
            pass

    dashboard_state['phase'] = 'monitoring'
    dashboard_state['discovery_msg'] = f'Spawning {len(active_countries)} instances on {CPU_CORES} Cores ({RAM_GB:.1f}GB RAM)...'
    
    for country in active_countries:
        spawn_country(country)
            
    dashboard_state['discovery_msg'] = 'Monitoring instances (Scheduler Active)...'
    
    if worker_count > 0:
        actual_worker_count = worker_count
    else:
        actual_worker_count = max(1, min(CPU_CORES * 2, 16))
        
    logger.info(f"Starting {actual_worker_count} scheduler workers for {len(active_countries)} instances.")
    
    dashboard_state['status'] = 'running'
    
    for i in range(actual_worker_count):
        t = threading.Thread(target=scheduler_worker, args=(i,), daemon=True)
        t.start()

def start_network(max_instances=20, ping_interval=60, ram_limit_mb=15, bandwidth_limit_kb=0, worker_count=0, selected_countries=""):
    global CONFIG_PING_INTERVAL, CONFIG_RAM_LIMIT_MB, CONFIG_BW_LIMIT_KB
    
    CONFIG_PING_INTERVAL = ping_interval
    CONFIG_RAM_LIMIT_MB = ram_limit_mb
    CONFIG_BW_LIMIT_KB = bandwidth_limit_kb

    if dashboard_state['status'] == 'running':
        logger.info("Live Reload Triggered: Diffing countries...")
        preferred = [c.strip().lower() for c in selected_countries.split(",") if c.strip()]
        
        # We need all available countries sorted by count to fill the rest
        all_available = list(G_COUNTRY_FINGERPRINTS.keys())
        all_available.sort(key=lambda x: len(G_COUNTRY_FINGERPRINTS[x]), reverse=True)
        
        desired_countries = []
        for p in preferred:
            if p in all_available and p not in desired_countries:
                desired_countries.append(p)
                if len(desired_countries) >= max_instances:
                    break
                    
        for c in all_available:
            if len(desired_countries) >= max_instances:
                break
            if c not in desired_countries:
                desired_countries.append(c)
                
        with QUEUE_LOCK:
            current_countries = [inst.country for inst in instances]
            
            # Remove instances not in desired
            for inst in instances[:]:
                if inst.country not in desired_countries:
                    logger.info(f"Live Reload: Removing {inst.country}")
                    inst.stop()
                    instances.remove(inst)
                    if inst.country in dashboard_state['instances']:
                        del dashboard_state['instances'][inst.country]
                        
            # Add instances in desired that are not current
            for c in desired_countries:
                if c not in current_countries:
                    logger.info(f"Live Reload: Adding {c}")
                    spawn_country(c)
                    
        return True
        
    global global_thread
    global_thread = threading.Thread(target=start_network_thread, args=(max_instances, ping_interval, ram_limit_mb, bandwidth_limit_kb, worker_count, selected_countries), daemon=True)
    global_thread.start()
    return True
