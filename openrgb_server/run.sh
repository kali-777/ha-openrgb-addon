#!/usr/bin/env bash
set -e

OPTIONS_FILE="/data/options.json"
CONFIG_DIR="/config/OpenRGB"
CONFIG_FILE="${CONFIG_DIR}/OpenRGB.json"

mkdir -p "${CONFIG_DIR}" /etc/udev/rules.d

# Keep ONLY /etc/udev/rules.d/60-openrgb.rules so OpenRGB sees neither missing nor duplicate udev rules
touch /etc/udev/rules.d/60-openrgb.rules
rm -f /usr/lib/udev/rules.d/60-openrgb.rules

# Read options from Home Assistant /data/options.json
SERVER_PORT=$(jq -r '.server_port // 6742' "${OPTIONS_FILE}")
SERVER_HOST=$(jq -r '.server_host // "0.0.0.0"' "${OPTIONS_FILE}")
LOG_LEVEL=$(jq -r '.log_level // "info"' "${OPTIONS_FILE}")
LIST_DEVICES=$(jq -r '.list_devices_on_start // true' "${OPTIONS_FILE}")
WIZ_WHITE_STRATEGY=$(jq -r '.wiz_white_strategy // "Average"' "${OPTIONS_FILE}")
EXTRA_ARGS=$(jq -r '.extra_args // ""' "${OPTIONS_FILE}")
ENABLE_DDC=$(jq -r '.enable_ddc // true' "${OPTIONS_FILE}")

DDC_PID=""

cleanup() {
    echo "Stopping background services..."
    if [ -n "${DDC_PID}" ]; then
        kill "${DDC_PID}" 2>/dev/null || true
    fi
}
trap cleanup EXIT SIGINT SIGTERM

echo "=================================================================="
echo " Starting OpenRGB SDK Server & DDC/CI Add-on (v1.3.3)"
echo "=================================================================="
echo "OpenRGB Version : $(openrgb --version 2>/dev/null | head -n 1 || echo 'OpenRGB 1.0+')"
echo "Bind Address    : ${SERVER_HOST}:${SERVER_PORT}"
echo "Config Directory: ${CONFIG_DIR}"
echo "I2C Bus Devices : $(ls -d /dev/i2c* 2>/dev/null | tr '\n' ' ' || echo 'None detected')"
echo "Security Notice : For DDC/CI monitor control via /dev/i2c-*, ensure 'Protection mode' is toggled OFF (Unprotected mode) in the add-on settings."

# Start Generic DDC/CI Monitor Control Service if enabled
if [ "${ENABLE_DDC}" = "true" ]; then
    echo "------------------------------------------------------------------"
    echo "Launching Generic DDC/CI Monitor Control Service..."
    python3 -u /ddc_service.py &
    DDC_PID=$!
    echo "DDC/CI Monitor Service started (PID: ${DDC_PID})"
fi

# Initialize OpenRGB.json if it does not exist yet
if [ ! -f "${CONFIG_FILE}" ]; then
    echo "{}" > "${CONFIG_FILE}"
fi

# Pre-flight reachability probe & automated model discovery for smart lights
echo "Checking network smart lights reachability..."
python3 - <<'EOF' "${OPTIONS_FILE}" "${CONFIG_FILE}" "${WIZ_WHITE_STRATEGY}"
import json
import os
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

opts_file = sys.argv[1]
cfg_file = sys.argv[2]
wiz_strategy = sys.argv[3]

with open(opts_file, "r") as f:
    opts = json.load(f)

wiz_raw = [ip.strip() for ip in opts.get("wiz_ips", []) if ip and ip.strip()]
yeelight_raw = [ip.strip() for ip in opts.get("yeelight_ips", []) if ip and ip.strip()]
kasa_raw = [ip.strip() for ip in opts.get("kasa_ips", []) if ip and ip.strip()]

YEELIGHT_MODEL_NAMES = {
    "stripe": "Yeelight Light Strip Plus",
    "color": "Mi LED Smart Bulb Color",
    "color3": "Mi LED Smart Bulb Color",
    "color4": "Mi LED Smart Bulb Color",
    "bslamp1": "Mi Bedside Lamp 1",
    "bslamp2": "Mi Bedside Lamp 2",
    "ceiling1": "Mi Ceiling Light",
}

WIZ_MODEL_NAMES = {
    "DMORGB": "Philips WiZ Light Bar (RGBW)",
    "DHRGB": "Philips WiZ Squire Lamp (RGBWW Dual-Head)",
    "SHRGB": "Philips WiZ Color Bulb (RGBW)",
    "SHRGB1C": "Philips WiZ Color Bulb (RGBW)",
    "SHRGB2C": "Philips WiZ Color Bulb (RGBW)",
    "SHTW": "Philips WiZ Tunable White Bulb",
    "SHTW1C": "Philips WiZ Tunable White Bulb",
    "SHTW2C": "Philips WiZ Tunable White Bulb",
    "SHDW": "Philips WiZ Dimmable White Bulb",
    "SOCKET": "Philips WiZ Smart Plug",
    "PLUG": "Philips WiZ Smart Plug",
    "HERA": "Philips WiZ Hero Lamp",
    "POLE": "Philips WiZ Pole Floor Light",
    "STRIP": "Philips WiZ Lightstrip (RGB)",
}

def ping_check(ip, count=5, timeout=4):
    try:
        res = subprocess.run(["ping", "-c", str(count), "-W", str(timeout), ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return res.returncode == 0
    except Exception:
        return False

def probe_wiz(ip):
    # 1. Multi-attempt UDP query (port 38899) with model & telemetry discovery
    for attempt in range(3):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(3.0)
            # Query getSystemConfig for hardware module and firmware version
            s.sendto(b'{"method":"getSystemConfig","params":{}}', (ip, 38899))
            sys_data, _ = s.recvfrom(2048)
            
            # Query getPilot for signal strength and current state
            rssi = None
            try:
                s.sendto(b'{"method":"getPilot","params":{}}', (ip, 38899))
                pilot_data, _ = s.recvfrom(1024)
                if pilot_data:
                    p_res = json.loads(pilot_data.decode("utf-8")).get("result", {})
                    rssi = p_res.get("rssi")
            except Exception:
                pass
            s.close()

            if sys_data:
                parsed = json.loads(sys_data.decode("utf-8"))
                res = parsed.get("result", {})
                mod_name = res.get("moduleName", "")
                fw = res.get("fwVersion", "")
                mac = res.get("mac", "")
                
                # Parse model identifier from moduleName (e.g. ESP25_DMORGB_31 -> DMORGB)
                raw_model = mod_name
                parts = mod_name.split("_")
                if len(parts) >= 2:
                    raw_model = parts[1]
                elif len(parts) == 1 and parts[0]:
                    raw_model = parts[0]
                
                friendly_model = WIZ_MODEL_NAMES.get(raw_model.upper(), raw_model if raw_model else "Philips WiZ")
                info_parts = [friendly_model]
                if raw_model and raw_model != friendly_model:
                    info_parts.append(f"model: {raw_model}")
                if fw:
                    info_parts.append(f"FW: {fw}")
                if rssi is not None:
                    info_parts.append(f"RSSI: {rssi} dBm")
                if mac:
                    info_parts.append(f"MAC: {mac}")
                
                extra = f"{info_parts[0]} ({', '.join(info_parts[1:])})" if len(info_parts) > 1 else info_parts[0]
                return (ip, True, extra)
        except Exception:
            pass

    # 2. Fallback to getPilot only if getSystemConfig was missed
    for attempt in range(2):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(3.0)
            s.sendto(b'{"method":"getPilot","params":{}}', (ip, 38899))
            pilot_data, _ = s.recvfrom(1024)
            s.close()
            if pilot_data:
                p_res = json.loads(pilot_data.decode("utf-8")).get("result", {})
                rssi = p_res.get("rssi")
                mac = p_res.get("mac")
                extra = f"Philips WiZ (RSSI: {rssi} dBm, MAC: {mac})" if rssi is not None else "Philips WiZ"
                return (ip, True, extra)
        except Exception:
            pass

    # 3. Multi-packet ICMP ping fallback (5 packets, 4s timeout)
    if ping_check(ip, count=5, timeout=4):
        return (ip, True, "Philips WiZ (Ping responsive)")
    return (ip, False, "Host unreachable / offline (UDP & ICMP timed out)")

def probe_yeelight(ip):
    # 1. Test TCP connect to port 55443 (3.5s timeout) and discover hardware model
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3.5)
    try:
        s.connect((ip, 55443))
        model_info = ""
        try:
            cmd = json.dumps({"id": 1, "method": "get_prop", "params": ["name", "model"]}) + "\r\n"
            s.sendall(cmd.encode("utf-8"))
            resp = json.loads(s.recv(1024).decode("utf-8"))
            if "result" in resp and len(resp["result"]) >= 2:
                d_name, d_model = resp["result"][0], resp["result"][1]
                friendly = YEELIGHT_MODEL_NAMES.get(d_model, d_model)
                model_info = f"{friendly} (model: {d_model})"
                if d_name:
                    model_info = f"{d_name} - {model_info}"
        except Exception:
            pass
        s.close()
        return (ip, True, model_info)
    except ConnectionRefusedError:
        return (ip, False, "Connection refused on port 55443 — LAN Control is disabled in Yeelight app")
    except socket.timeout:
        return (ip, False, "TCP port 55443 timed out — verify device power and LAN Control in Yeelight app")
    except Exception as e:
        err_msg = str(e).lower()
        if "refused" in err_msg:
            return (ip, False, "Connection refused on port 55443 — LAN Control is disabled in Yeelight app")
        elif "timed out" in err_msg or "timeout" in err_msg:
            return (ip, False, "TCP port 55443 timed out — verify device power and LAN Control in Yeelight app")
        return (ip, False, f"TCP 55443 error: {e}")

def probe_kasa(ip):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3.0)
        s.connect((ip, 9999))
        s.close()
        return (ip, True, "Kasa Connected")
    except Exception:
        pass
    if ping_check(ip, count=5, timeout=4):
        return (ip, True, "Ping responsive")
    return (ip, False, "Host unreachable / offline")

def run_probes(ip_list, probe_fn, dev_type):
    with ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(probe_fn, ip_list))
    online = []
    for ip, ok, extra in results:
        if ok:
            online.append((ip, extra))
        else:
            print(f"[OpenRGB] Safeguard: {dev_type} {ip} is unavailable ({extra}); skipping from config to prevent 60s DetectionManager freeze.")
    return online

online_wiz = run_probes(wiz_raw, probe_wiz, "Philips WiZ")
online_yeelight = run_probes(yeelight_raw, probe_yeelight, "Xiaomi Yeelight")
online_kasa = run_probes(kasa_raw, probe_kasa, "TP-Link Kasa")

cfg = {}
if os.path.exists(cfg_file):
    try:
        with open(cfg_file, "r") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}

if online_wiz:
    cfg["PhilipsWizDevices"] = {
        "devices": [{
            "ip": ip,
            "selected_white_strategy": wiz_strategy,
            "use_cool_white": False,
            "use_warm_white": False
        } for ip, _ in online_wiz]
    }
else:
    cfg["PhilipsWizDevices"] = None

if online_yeelight:
    # Always enforce music_mode: false to prevent reverse-socket deadlock in Docker
    cfg["YeelightDevices"] = {
        "devices": [{
            "ip": ip,
            "music_mode": False
        } for ip, _ in online_yeelight]
    }
else:
    cfg["YeelightDevices"] = None

if online_kasa:
    cfg["KasaSmartDevices"] = {
        "devices": [{"ip": ip} for ip, _ in online_kasa]
    }
else:
    cfg["KasaSmartDevices"] = None

if "Detectors" not in cfg or not isinstance(cfg["Detectors"], dict):
    cfg["Detectors"] = {"detectors": {}}
if "detectors" not in cfg["Detectors"]:
    cfg["Detectors"]["detectors"] = {}

cfg["Detectors"]["detectors"]["HyperX DuoCast"] = True
cfg["Detectors"]["detectors"]["HyperX Quadcast S"] = True
cfg["Detectors"]["detectors"]["HyperX QuadCast 2 S"] = True

with open(cfg_file, "w") as f:
    json.dump(cfg, f, indent=4)

if online_wiz:
    print("Configured Online Philips WiZ Devices:")
    for ip, extra in online_wiz:
        print(f"  - {ip}: {extra if extra else 'Philips WiZ'}")
else:
    print("Configured Online Philips WiZ IPs : None")

if online_yeelight:
    print("Configured Online Yeelight Devices:")
    for ip, extra in online_yeelight:
        print(f"  - {ip}: {extra if extra else 'Yeelight Device'}")
else:
    print("Configured Online Yeelight IPs    : None")

if online_kasa:
    print("Configured Online Kasa Smart Devices:")
    for ip, extra in online_kasa:
        print(f"  - {ip}: {extra if extra else 'TP-Link Kasa'}")
else:
    print("Configured Online Kasa Smart IPs  : None")
EOF

echo "------------------------------------------------------------------"
if [ "${LIST_DEVICES}" = "true" ]; then
    echo "Detected OpenRGB Devices (use these IDs in LedFx):"
    QT_QPA_PLATFORM=offscreen openrgb --config "${CONFIG_DIR}" --noautoconnect --list-devices 2>&1 \
      | grep --line-buffered -vE '(\[Dialog \]|recv_select failed receiving magic)' || true
    echo "------------------------------------------------------------------"
fi

echo "Launching OpenRGB SDK Server on ${SERVER_HOST}:${SERVER_PORT}..."

if [ "${LOG_LEVEL}" = "debug" ] || [ "${LOG_LEVEL}" = "trace" ]; then
    openrgb \
        --config "${CONFIG_DIR}" \
        --noautoconnect \
        --server \
        --server-host "${SERVER_HOST}" \
        --server-port "${SERVER_PORT}" \
        --loglevel 6 \
        ${EXTRA_ARGS} &
    OPENRGB_PID=$!
    wait ${OPENRGB_PID}
else
    openrgb \
        --config "${CONFIG_DIR}" \
        --noautoconnect \
        --server \
        --server-host "${SERVER_HOST}" \
        --server-port "${SERVER_PORT}" \
        ${EXTRA_ARGS} 2>&1 | grep --line-buffered -vE '(\[Dialog \]|recv_select failed receiving magic)' &
    OPENRGB_PID=$!
    wait ${OPENRGB_PID}
fi
