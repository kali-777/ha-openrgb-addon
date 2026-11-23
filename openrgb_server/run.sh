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
echo " Starting OpenRGB SDK Server & DDC/CI Add-on (v1.1.8)"
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

# Pre-flight reachability probe for configured network smart lights (WiZ, Yeelight, Kasa)
# Uses multi-packet ping and direct port checks to handle high-jitter 2.4GHz Wi-Fi and prevent 60s DetectionManager freezes
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

def ping_check(ip, count=4, timeout=2):
    try:
        res = subprocess.run(["ping", "-c", str(count), "-W", str(timeout), ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return res.returncode == 0
    except Exception:
        return False

def probe_wiz(ip):
    # 1. Quick UDP getPilot test (port 38899)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1.5)
        s.sendto(b'{"method":"getPilot","params":{}}', (ip, 38899))
        data, _ = s.recvfrom(1024)
        s.close()
        if data:
            return (ip, True, "")
    except Exception:
        pass
    # 2. Multi-packet ICMP ping fallback
    if ping_check(ip, count=4, timeout=2):
        return (ip, True, "")
    return (ip, False, "Host unreachable / offline")

def probe_yeelight(ip):
    # 1. Test TCP connect to port 55443 (LAN Control port)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2.5)
    try:
        s.connect((ip, 55443))
        s.close()
        return (ip, True, "")
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
    # 1. Test TCP connect to port 9999
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect((ip, 9999))
        s.close()
        return (ip, True, "")
    except Exception:
        pass
    # 2. Multi-packet ICMP ping fallback
    if ping_check(ip, count=4, timeout=2):
        return (ip, True, "")
    return (ip, False, "Host unreachable / offline")

def run_probes(ip_list, probe_fn, dev_type):
    with ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(probe_fn, ip_list))
    online = []
    for ip, ok, err_reason in results:
        if ok:
            online.append(ip)
        else:
            print(f"[OpenRGB] Safeguard: {dev_type} {ip} is unavailable ({err_reason}); skipping from config to prevent 60s DetectionManager freeze.")
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
        } for ip in online_wiz]
    }
else:
    cfg["PhilipsWizDevices"] = None

if online_yeelight:
    # Always enforce music_mode: false. In Docker / HAOS, music_mode: true triggers OpenRGB tcp_server_listen()
    # reverse-connection wait on the container's internal hostname, which deadlocks DetectionManager for 60 seconds.
    cfg["YeelightDevices"] = {
        "devices": [{
            "ip": ip,
            "music_mode": False
        } for ip in online_yeelight]
    }
else:
    cfg["YeelightDevices"] = None

if online_kasa:
    cfg["KasaSmartDevices"] = {
        "devices": [{"ip": ip} for ip in online_kasa]
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

print(f"Configured Online Philips WiZ IPs : {', '.join(online_wiz) if online_wiz else 'None'}")
print(f"Configured Online Yeelight IPs    : {', '.join(online_yeelight) if online_yeelight else 'None'}")
print(f"Configured Online Kasa Smart IPs  : {', '.join(online_kasa) if online_kasa else 'None'}")
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
