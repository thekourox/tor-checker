from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import core
import os
import json
import subprocess
import threading

app = FastAPI(title="Tor VPN Backend Panel")

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure static directory exists
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/status")
async def get_status():
    return core.dashboard_state

CONFIG_FILE = "config.json"

def get_auto_config():
    tier = core.HARDWARE_TIER
    if tier == 'LOW':
        return {
            'max_instances': 15,
            'ping_interval': 60,
            'ram_limit_mb': 15,
            'bandwidth_limit_kb': 200,
            'worker_count': 2,
            'selected_countries': ""
        }
    elif tier == 'MID':
        return {
            'max_instances': 40,
            'ping_interval': 30,
            'ram_limit_mb': 30,
            'bandwidth_limit_kb': 0,
            'worker_count': 0,
            'selected_countries': ""
        }
    else:
        return {
            'max_instances': 100,
            'ping_interval': 15,
            'ram_limit_mb': 50,
            'bandwidth_limit_kb': 0,
            'worker_count': 16,
            'selected_countries': ""
        }

class StartConfig(BaseModel):
    max_instances: int = None
    ping_interval: int = None
    ram_limit_mb: int = None
    bandwidth_limit_kb: int = None
    worker_count: int = None
    selected_countries: str = ""

@app.on_event("startup")
async def startup_event():
    # Kill any zombie tor processes from previous crashes
    try:
        if os.name == 'nt':
            subprocess.run(["taskkill", "/F", "/IM", "tor.exe"], capture_output=True)
        else:
            subprocess.run(["killall", "tor"], capture_output=True)
    except:
        pass

    if not os.path.exists(CONFIG_FILE):
        auto_cfg = get_auto_config()
        with open(CONFIG_FILE, "w") as f:
            json.dump(auto_cfg, f)
            
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            
            # Merge missing keys from auto_config for backward compatibility
            auto_cfg = get_auto_config()
            for k, v in auto_cfg.items():
                if k not in data or data[k] is None:
                    data[k] = v
                    
            config = StartConfig(**data)
            core.start_network(
                max_instances=config.max_instances,
                ping_interval=config.ping_interval,
                ram_limit_mb=config.ram_limit_mb,
                bandwidth_limit_kb=config.bandwidth_limit_kb,
                worker_count=config.worker_count,
                selected_countries=config.selected_countries
            )
    except:
        pass

@app.on_event("shutdown")
async def shutdown_event():
    # Final cleanup to ensure no Tor zombies are left behind
    try:
        core.cleanup_all_instances()
    except:
        pass

@app.get("/api/settings")
async def get_settings():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return get_auto_config()

@app.get("/api/scan_countries")
async def scan_countries():
    # If already populated, return immediately
    if core.G_COUNTRY_FINGERPRINTS:
        return {"status": "success", "countries": list(core.G_COUNTRY_FINGERPRINTS.keys())}
        
    import platform
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
        country_counts, _ = core.discover_exit_countries(tor_cmd)
        return {"status": "success", "countries": list(country_counts.keys())}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/start")
async def start_network_api(config: StartConfig):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config.dict(), f, indent=4)
        
    if core.dashboard_state['status'] == 'running':
        return {"status": "error", "message": "Already running"}
        
    core.dashboard_state['instances'] = {}
    core.start_network(
        max_instances=config.max_instances,
        ping_interval=config.ping_interval,
        ram_limit_mb=config.ram_limit_mb,
        bandwidth_limit_kb=config.bandwidth_limit_kb,
        worker_count=config.worker_count,
        selected_countries=config.selected_countries
    )
    return {"status": "success", "message": "Network startup initiated"}

@app.post("/api/stop")
async def stop_network():
    core.stop_all()
    return {"status": "success", "message": "Network stopped"}

@app.post("/api/generate_xray")
async def generate_xray():
    try:
        if not os.path.exists("port_mapping.json"):
            return {"status": "error", "message": "No active instances found"}
            
        with open("port_mapping.json", "r") as f:
            mapping = json.load(f)
            
        outbounds = []
        routing_rules = []
        
        server_ip = "172.17.0.1" if platform.system() == 'Linux' else "127.0.0.1"
        
        for port, country in mapping.items():
            tag_name = f"Tor_{country.upper()}"
            outbounds.append({
                "tag": tag_name,
                "protocol": "socks",
                "settings": {
                    "servers": [{"address": server_ip, "port": int(port)}]
                }
            })
            routing_rules.append({
                "type": "field",
                "outboundTag": tag_name,
                "domain": [f"geosite:{country.lower()}"]
            })
            
        config = {
            "remarks": "Auto-Generated by Tor Manager for 3x-ui",
            "outbounds": outbounds,
            "routing": {
                "rules": routing_rules
            }
        }
        
        with open("optimized_config.json", "w") as f:
            json.dump(config, f, indent=4)
            
        return {"status": "success", "message": f"Config generated for {len(outbounds)} nodes!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=54321)
