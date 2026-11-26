#!/usr/bin/env bash
set -e

OPTIONS_FILE="/data/options.json"
CONFIG_DIR="/config/OpenRGB"
CONFIG_FILE="${CONFIG_DIR}/OpenRGB.json"
GHOST_FILE="${CONFIG_DIR}/ghost_devices.json"

mkdir -p "${CONFIG_DIR}" /etc/udev/rules.d

# Ensure full read/write permissions for all USB and HIDRAW devices
chmod -R a+rw /dev/hidraw* /dev/bus/usb 2>/dev/null || true

# Generate official OpenRGB udev rules if missing or empty, avoiding duplicate rule warnings
if [ ! -s /etc/udev/rules.d/60-openrgb.rules ]; then
    echo "Generating OpenRGB udev rules..."
    QT_QPA_PLATFORM=offscreen openrgb --generate-udev-rules /etc/udev/rules.d/60-openrgb.rules 2>/dev/null || touch /etc/udev/rules.d/60-openrgb.rules
fi
rm -f /usr/lib/udev/rules.d/60-openrgb.rules /lib/udev/rules.d/60-openrgb.rules 2>/dev/null || true

# Read options from Home Assistant /data/options.json
SERVER_PORT=$(jq -r '.server_port // 6742' "${OPTIONS_FILE}")
SERVER_HOST=$(jq -r '.server_host // "0.0.0.0"' "${OPTIONS_FILE}")
LOG_LEVEL=$(jq -r '.log_level // "info"' "${OPTIONS_FILE}")
LIST_DEVICES=$(jq -r '.list_devices_on_start // true' "${OPTIONS_FILE}")
WIZ_WHITE_STRATEGY=$(jq -r '.wiz_white_strategy // "Average"' "${OPTIONS_FILE}")
EXTRA_ARGS=$(jq -r '.extra_args // ""' "${OPTIONS_FILE}")
ENABLE_DDC=$(jq -r '.enable_ddc // true' "${OPTIONS_FILE}")

DDC_PID=""
GHOST_PID=""

cleanup() {
    echo "Stopping background services..."
    if [ -n "${GHOST_PID}" ]; then
        kill "${GHOST_PID}" 2>/dev/null || true
    fi
    if [ -n "${DDC_PID}" ]; then
        kill "${DDC_PID}" 2>/dev/null || true
    fi
}
trap cleanup EXIT SIGINT SIGTERM

echo "=================================================================="
echo " Starting OpenRGB SDK Server & DDC/CI Add-on (v1.4.1)"
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

# Pre-flight reachability probe & persistent ID ghost responder preparation
echo "Checking network smart lights reachability & preparing persistent IDs..."
python3 - <<'EOF' "${OPTIONS_FILE}" "${CONFIG_FILE}" "${CONFIG_DIR}" "${WIZ_WHITE_STRATEGY}"
import json
import os
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

opts_file = sys.argv[1]
cfg_file = sys.argv[2]
config_dir = sys.argv[3]
wiz_strategy = sys.argv[4]

cache_file = os.path.join(config_dir, "device_cache.json")
ghost_file = os.path.join(config_dir, "ghost_devices.json")

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

# Seed known persistent Goa Home hardware signatures
cache = {
    "192.168.2.65": {"type": "wiz", "model": "DMORGB", "mac": "9877d5421304", "moduleName": "ESP25_DMORGB_31", "fwVersion": "1.39.2"},
    "192.168.2.56": {"type": "wiz", "model": "SHRGB", "mac": "d8a011f84f49", "moduleName": "ESP25_SHRGB_01", "fwVersion": "1.38.0"},
    "192.168.2.57": {"type": "wiz", "model": "DHRGB", "mac": "9877d5864a8e", "moduleName": "ESP25_DHRGB_01", "fwVersion": "1.39.2"},
    "192.168.2.51": {"type": "yeelight", "model": "stripe", "name": "Yeelight Light Strip Plus"},
    "192.168.2.52": {"type": "yeelight", "model": "color", "name": "Mi LED Smart Bulb Color"},
    "192.168.2.53": {"type": "yeelight", "model": "color", "name": "Mi LED Smart Bulb Color"},
    "192.168.2.54": {"type": "yeelight", "model": "bslamp1", "name": "Mi Bedside Lamp 1"},
}

if os.path.exists(cache_file):
    try:
        with open(cache_file, "r") as f:
            disk_cache = json.load(f)
            if isinstance(disk_cache, dict):
                cache.update(disk_cache)
    except Exception:
        pass

def ping_check(ip, count=4, timeout=3):
    try:
        res = subprocess.run(["ping", "-c", str(count), "-W", str(timeout), ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return res.returncode == 0
    except Exception:
        return False

def probe_wiz(ip):
    for attempt in range(2):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(2.5)
            s.sendto(b'{"method":"getSystemConfig","params":{}}', (ip, 38899))
            sys_data, _ = s.recvfrom(2048)
            
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
                return (ip, True, extra, {"type": "wiz", "model": raw_model, "mac": mac, "moduleName": mod_name, "fwVersion": fw})
        except Exception:
            pass

    if ping_check(ip, count=3, timeout=2):
        return (ip, True, "Philips WiZ (Ping responsive)", {})
    return (ip, False, "Offline / wall switch turned off", {})

def probe_yeelight(ip):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2.5)
    try:
        s.connect((ip, 55443))
        d_name, d_model = "", "color"
        try:
            cmd = json.dumps({"id": 1, "method": "get_prop", "params": ["name", "model"]}) + "\r\n"
            s.sendall(cmd.encode("utf-8"))
            resp = json.loads(s.recv(1024).decode("utf-8"))
            if "result" in resp and len(resp["result"]) >= 2:
                d_name, d_model = resp["result"][0], resp["result"][1]
        except Exception:
            pass
        s.close()
        friendly = YEELIGHT_MODEL_NAMES.get(d_model, d_model)
        model_info = f"{friendly} (model: {d_model})"
        if d_name:
            model_info = f"{d_name} - {model_info}"
        return (ip, True, model_info, {"type": "yeelight", "model": d_model, "name": d_name or friendly})
    except Exception:
        return (ip, False, "Offline / wall switch turned off", {})

def probe_kasa(ip):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.5)
        s.connect((ip, 9999))
        s.close()
        return (ip, True, "Kasa Connected", {})
    except Exception:
        pass
    if ping_check(ip, count=3, timeout=2):
        return (ip, True, "Ping responsive", {})
    return (ip, False, "Host unreachable / offline", {})

with ThreadPoolExecutor(max_workers=10) as ex:
    wiz_results = list(ex.map(probe_wiz, wiz_raw))
    yeelight_results = list(ex.map(probe_yeelight, yeelight_raw))
    kasa_results = list(ex.map(probe_kasa, kasa_raw))

ghost_wiz = []
ghost_yeelight = []

# Process WiZ results
for ip, ok, extra, dev_data in wiz_results:
    if ok and dev_data:
        cache[ip] = dev_data
    elif not ok:
        cached = cache.get(ip, {})
        ghost_wiz.append({
            "ip": ip,
            "mac": cached.get("mac", "d8a011" + "".join(f"{int(o):02x}" for o in ip.split(".")[1:])),
            "moduleName": cached.get("moduleName", "ESP25_SHRGB_01"),
            "fwVersion": cached.get("fwVersion", "1.39.0")
        })

# Process Yeelight results
for ip, ok, extra, dev_data in yeelight_results:
    if ok and dev_data:
        cache[ip] = dev_data
    elif not ok:
        cached = cache.get(ip, {})
        ghost_yeelight.append({
            "ip": ip,
            "model": cached.get("model", "color"),
            "name": cached.get("name", "Yeelight Device")
        })

# Save persistent cache
try:
    with open(cache_file, "w") as f:
        json.dump(cache, f, indent=4)
except Exception:
    pass

# Save ghost configuration for offline devices
ghost_config = {
    "wiz": ghost_wiz,
    "yeelight": ghost_yeelight
}
try:
    with open(ghost_file, "w") as f:
        json.dump(ghost_config, f, indent=4)
except Exception:
    pass

# Build OpenRGB.json with ALL configured IPs in their EXACT order
cfg = {}
if os.path.exists(cfg_file):
    try:
        with open(cfg_file, "r") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}

if wiz_raw:
    cfg["PhilipsWizDevices"] = {
        "devices": [{
            "ip": ip,
            "selected_white_strategy": wiz_strategy,
            "use_cool_white": False,
            "use_warm_white": False
        } for ip in wiz_raw]
    }
else:
    cfg["PhilipsWizDevices"] = None

if yeelight_raw:
    cfg["YeelightDevices"] = {
        "devices": [{
            "ip": ip,
            "music_mode": False
        } for ip in yeelight_raw]
    }
else:
    cfg["YeelightDevices"] = None

online_kasa = [ip for ip, ok, _, _ in kasa_results if ok]
if online_kasa:
    cfg["KasaSmartDevices"] = {
        "devices": [{"ip": ip} for ip in online_kasa]
    }
else:
    cfg["KasaSmartDevices"] = None

# Remove restrictive detector overrides to allow OpenRGB to run all USB HID detectors natively
cfg.pop("Detectors", None)
cfg.pop("detectors", None)

with open(cfg_file, "w") as f:
    json.dump(cfg, f, indent=4)

print("------------------------------------------------------------------")
print(f"Configured Philips WiZ Devices ({len(wiz_raw)} configured):")
for ip, ok, extra, _ in wiz_results:
    if ok:
        print(f"  - {ip}: {extra} [ONLINE]")
    else:
        cached = cache.get(ip, {})
        m = cached.get('moduleName', 'WiZ Bulb')
        print(f"  - {ip}: {m} [OFFLINE / WALL SWITCH OFF] -> Ghost Responder Active (ID preserved for LedFx)")

print(f"Configured Xiaomi Yeelight Devices ({len(yeelight_raw)} configured):")
for ip, ok, extra, _ in yeelight_results:
    if ok:
        print(f"  - {ip}: {extra} [ONLINE]")
    else:
        cached = cache.get(ip, {})
        m = cached.get('name', 'Yeelight Device')
        print(f"  - {ip}: {m} [OFFLINE / WALL SWITCH OFF] -> Ghost Responder Active (ID preserved for LedFx)")

print("------------------------------------------------------------------")
EOF

# Start Ghost Responder daemon if any devices are offline to guarantee static OpenRGB IDs
if [ -f "${GHOST_FILE}" ]; then
    HAS_GHOSTS=$(jq '(.wiz | length) + (.yeelight | length)' "${GHOST_FILE}" 2>/dev/null || echo "0")
    if [ "${HAS_GHOSTS}" -gt 0 ]; then
        echo "Launching OpenRGB Ghost Responder to protect LedFx device IDs..."
        python3 -u /ghost_responder.py &
        GHOST_PID=$!
        sleep 1
        echo "Ghost Responder active (PID: ${GHOST_PID})"
    else
        echo "All network devices are online. Ghost Responder not needed."
    fi
fi

echo "------------------------------------------------------------------"
echo "Connected USB & HIDRAW Devices:"
lsusb 2>/dev/null || echo "lsusb unavailable"
ls -la /dev/hidraw* 2>/dev/null || echo "No /dev/hidraw nodes found"
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
