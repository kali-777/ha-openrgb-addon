#!/usr/bin/env python3
"""
Generic DDC/CI Monitor Controller for Home Assistant OS
Provides:
  1. REST API on port 6743 (by default) for direct input/brightness/volume/mute/power switching
  2. Home Assistant MQTT Auto-Discovery (select, number, switch, button entities)
  3. Dynamic naming standard: <vendor>_<model>_monitor_<feature> (e.g., asus_va34vcpsr_monitor_input_source)
  4. Authentication support for Home Assistant Mosquitto broker
Works dynamically with any monitor supported by ddcutil.
"""

import sys
import os
import json
import time
import re
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

OPTIONS_FILE = "/data/options.json"
SERVICES_FILE = "/data/services/mqtt.json"

DDC_PORT = 6743
MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883
MQTT_USER = None
MQTT_PASS = None
POLL_INTERVAL = 60
ENABLE_MQTT = True

# Load options from Home Assistant
if os.path.exists(OPTIONS_FILE):
    try:
        with open(OPTIONS_FILE, "r") as f:
            opts = json.load(f)
            DDC_PORT = int(opts.get("ddc_port", 6743))
            ENABLE_MQTT = bool(opts.get("ddc_mqtt_discovery", True))
            POLL_INTERVAL = int(opts.get("ddc_poll_interval", 60))
            MQTT_USER = opts.get("mqtt_username") or None
            MQTT_PASS = opts.get("mqtt_password") or None
    except Exception as e:
        print(f"[DDC] Error loading options.json: {e}", file=sys.stderr)

# Auto-detect MQTT credentials from Supervisor service if not manually configured
if (not MQTT_USER or not MQTT_PASS) and os.path.exists(SERVICES_FILE):
    try:
        with open(SERVICES_FILE, "r") as f:
            svc = json.load(f)
            MQTT_HOST = svc.get("host", MQTT_HOST)
            MQTT_PORT = int(svc.get("port", MQTT_PORT))
            MQTT_USER = svc.get("username", MQTT_USER)
            MQTT_PASS = svc.get("password", MQTT_PASS)
            print(f"[DDC] Detected MQTT credentials from Supervisor service: user '{MQTT_USER}'")
    except Exception as e:
        print(f"[DDC] Note: Could not read {SERVICES_FILE}: {e}", file=sys.stderr)

# Fallback environment variables
MQTT_USER = os.environ.get("MQTT_USER", MQTT_USER)
MQTT_PASS = os.environ.get("MQTT_PASSWORD", MQTT_PASS)

# Common 3-letter EDID manufacturer lookup table
MFG_LOOKUP = {
    "AUS": "ASUS",
    "SAM": "Samsung",
    "DEL": "Dell",
    "GSM": "LG",
    "LGD": "LG",
    "ACR": "Acer",
    "BNQ": "BenQ",
    "BEN": "BenQ",
    "AOC": "AOC",
    "HWP": "HP",
    "HPN": "HP",
    "LEN": "Lenovo",
    "MSI": "MSI",
    "GIG": "Gigabyte",
    "VSC": "ViewSonic",
    "SNY": "Sony",
    "NEC": "NEC",
    "IIY": "Iiyama",
    "APP": "Apple",
    "PHL": "Philips",
}

VESA_INPUT_MAP = {
    0x01: "VGA-1",
    0x02: "VGA-2",
    0x03: "DVI-1",
    0x04: "DVI-2",
    0x05: "Composite-1",
    0x06: "Composite-2",
    0x07: "S-Video-1",
    0x08: "S-Video-2",
    0x09: "Tuner-1",
    0x0A: "Tuner-2",
    0x0B: "Component-1",
    0x0C: "Component-2",
    0x0D: "Component-3",
    0x0E: "DisplayPort-0",
    0x0F: "DisplayPort-1",
    0x10: "DisplayPort-2",
    0x11: "HDMI-1",
    0x12: "HDMI-2",
    0x13: "USB-C",
    0x14: "HDMI-3",
    0x15: "HDMI-4",
    0x16: "DisplayPort-3",
    0x17: "DisplayPort-4",
}

INPUT_NAME_TO_HEX = {name.lower(): code for code, name in VESA_INPUT_MAP.items()}
INPUT_NAME_TO_HEX.update({
    "dp": 0x0F,
    "dp1": 0x0F,
    "dp2": 0x10,
    "hdmi": 0x11,
    "hdmi1": 0x11,
    "hdmi2": 0x12,
    "hdmi3": 0x14,
    "usbc": 0x13,
    "usb-c": 0x13,
    "typec": 0x13,
    "type-c": 0x13,
    "work": 0x13,
    "haos": 0x0F,
    "windows": 0x11,
})


def run_ddcutil(*args):
    cmd = ["ddcutil"] + list(args)
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return res.returncode, res.stdout, res.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout waiting for ddcutil"
    except Exception as e:
        return -1, "", str(e)


def clean_identifier(text):
    return re.sub(r"[^a-zA-Z0-9_]", "_", text.strip()).strip("_").lower()


class MonitorManager:
    def __init__(self):
        self.monitors = []
        self.lock = threading.Lock()

    def detect_monitors(self):
        code, out, err = run_ddcutil("detect")
        monitors = []

        # ddcutil detect often returns non-zero when some internal I2C buses return warnings,
        # but out still contains valid Display blocks. Check if any Display was found!
        if not out or "Display" not in out:
            print(f"[DDC] No monitors detected in output (exit code {code}). Stderr: {err.strip()}", file=sys.stderr)
            return monitors

        blocks = re.split(r"\n(?=Display\s+\d+)", out)
        for block in blocks:
            if not block.strip().startswith("Display"):
                continue

            disp_match = re.search(r"Display\s+(\d+)", block)
            if not disp_match:
                continue
            disp_id = int(disp_match.group(1))

            bus_match = re.search(r"I2C bus:\s+([^\n]+)", block)
            bus = bus_match.group(1).strip() if bus_match else ""

            mfg_match = re.search(r"Mfg id:\s+([^\n]+)", block)
            mfg_raw = mfg_match.group(1).strip() if mfg_match else "Generic"
            # Parse manufacturer ID (e.g. 'AUS - UNK' -> 'ASUS')
            mfg_code = mfg_raw.split("-")[0].strip().split()[0].upper()
            mfg = MFG_LOOKUP.get(mfg_code, mfg_raw.split("-")[0].strip() or "Generic")

            model_match = re.search(r"Model:\s+([^\n]+)", block)
            model = model_match.group(1).strip() if model_match else f"Monitor_{disp_id}"

            sn_match = re.search(r"Serial number:\s+([^\n]+)", block)
            sn = sn_match.group(1).strip() if sn_match else f"disp{disp_id}"
            clean_sn = re.sub(r"[^A-Za-z0-9_-]", "_", sn)

            mfg_clean = clean_identifier(mfg)
            model_clean = clean_identifier(model)
            # Standard prefix requested: <vendor>_<model>_monitor
            entity_prefix = f"{mfg_clean}_{model_clean}_monitor"
            device_id = f"ddc_{mfg_clean}_{model_clean}_{clean_sn.lower()}"

            cur_input_hex = self.get_vcp(disp_id, 0x60)
            cur_input_name = VESA_INPUT_MAP.get(cur_input_hex, f"0x{cur_input_hex:02x}" if cur_input_hex is not None else "Unknown")
            cur_brightness = self.get_vcp(disp_id, 0x10)
            cur_contrast = self.get_vcp(disp_id, 0x12)
            cur_volume = self.get_vcp(disp_id, 0x62)
            cur_mute_val = self.get_vcp(disp_id, 0x8D)
            cur_mute = (cur_mute_val == 1) if cur_mute_val is not None else False

            supported_inputs = self.query_supported_inputs(disp_id)
            if not supported_inputs:
                supported_inputs = [0x0F, 0x10, 0x11, 0x12, 0x13]

            input_options = []
            for h in supported_inputs:
                name = VESA_INPUT_MAP.get(h, f"0x{h:02x}")
                if name not in input_options:
                    input_options.append(name)

            mon = {
                "display": disp_id,
                "bus": bus,
                "mfg": mfg,
                "model": model,
                "serial": clean_sn,
                "entity_prefix": entity_prefix,
                "device_id": device_id,
                "device_name": f"{mfg} {model} Monitor",
                "current_input": f"0x{cur_input_hex:02x}" if cur_input_hex is not None else None,
                "current_input_name": cur_input_name,
                "supported_input_codes": [f"0x{h:02x}" for h in supported_inputs],
                "input_options": input_options,
                "brightness": cur_brightness,
                "contrast": cur_contrast,
                "volume": cur_volume,
                "mute": cur_mute,
                "has_audio": (cur_volume is not None),
                "has_mute": (cur_mute_val is not None),
            }
            monitors.append(mon)
            print(f"[DDC] Discovered: Display {disp_id} - {mfg} {model} (SN: {clean_sn}) on {bus}")
            print(f"[DDC]   Entity Prefix: {entity_prefix} | Current Input: {cur_input_name} | Audio: {mon['has_audio']}")

        with self.lock:
            self.monitors = monitors
        return monitors

    def query_supported_inputs(self, disp_id):
        code, out, _ = run_ddcutil("--display", str(disp_id), "capabilities")
        inputs = []
        if out:
            cap_match = re.search(r"60\(([^)]+)\)", out)
            if cap_match:
                for token in cap_match.group(1).split():
                    try:
                        val = int(token, 16)
                        if val not in inputs:
                            inputs.append(val)
                    except ValueError:
                        pass
        return inputs

    def get_vcp(self, disp_id, vcp_code):
        vcp_hex = f"0x{vcp_code:02x}"
        code, out, _ = run_ddcutil("--display", str(disp_id), "getvcp", vcp_hex, "--terse")
        if out:
            parts = out.strip().split()
            if len(parts) >= 4:
                try:
                    return int(parts[3])
                except ValueError:
                    pass
        return None

    def set_vcp(self, disp_id, vcp_code, value):
        vcp_hex = f"0x{vcp_code:02x}" if isinstance(vcp_code, int) else str(vcp_code)
        val_hex = f"0x{value:02x}" if isinstance(value, int) else str(value)
        code, out, err = run_ddcutil("--display", str(disp_id), "--noverify", "setvcp", vcp_hex, val_hex)
        return code == 0, out if code == 0 else err

    def set_input(self, disp_id, input_target):
        val = None
        if isinstance(input_target, int):
            val = input_target
        elif isinstance(input_target, str):
            clean = input_target.strip().lower()
            if clean in INPUT_NAME_TO_HEX:
                val = INPUT_NAME_TO_HEX[clean]
            elif clean.startswith("0x"):
                try:
                    val = int(clean, 16)
                except ValueError:
                    pass
            else:
                try:
                    val = int(clean, 10)
                except ValueError:
                    pass

        if val is None:
            return False, f"Unknown input target '{input_target}'"

        ok, msg = self.set_vcp(disp_id, 0x60, val)
        if ok:
            for m in self.monitors:
                if m["display"] == disp_id:
                    m["current_input"] = f"0x{val:02x}"
                    m["current_input_name"] = VESA_INPUT_MAP.get(val, f"0x{val:02x}")
        return ok, msg

    def set_mute(self, disp_id, mute_on):
        val = 1 if mute_on else 2
        ok, msg = self.set_vcp(disp_id, 0x8D, val)
        if ok:
            for m in self.monitors:
                if m["display"] == disp_id:
                    m["mute"] = mute_on
        return ok, msg


manager = MonitorManager()


class MQTTClientManager:
    def __init__(self, monitor_mgr):
        self.mgr = monitor_mgr
        self.client = None
        self.connected = False

    def start(self):
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            print("[DDC] paho-mqtt not installed; skipping MQTT discovery.", file=sys.stderr)
            return

        def on_connect(*args):
            # Support both CallbackAPIVersion.VERSION2 (client, userdata, flags, rc, props)
            # and VERSION1 (client, userdata, flags, rc)
            rc = args[3] if len(args) >= 4 else args[-1]
            code = rc.value if hasattr(rc, "value") else (int(rc) if isinstance(rc, int) else 0)
            if code == 0:
                print("[DDC] Connected successfully to MQTT broker. Publishing HA Discovery...")
                self.connected = True
                self.publish_discovery()
                self.publish_states()
            else:
                print(f"[DDC] MQTT connection failed with code {code} ({rc})", file=sys.stderr)

        def on_message(client, userdata, msg):
            try:
                topic = msg.topic
                payload = msg.payload.decode("utf-8").strip()
                print(f"[DDC] MQTT message received: {topic} -> {payload}")

                parts = topic.split("/")
                if len(parts) >= 5 and parts[0] == "ha_openrgb" and parts[1] == "ddc":
                    dev_id = parts[2]
                    comp = parts[3]
                    mon = next((m for m in self.mgr.monitors if m["device_id"] == dev_id), None)
                    if not mon:
                        return

                    disp_id = mon["display"]

                    if comp == "input":
                        ok, _ = self.mgr.set_input(disp_id, payload)
                        if ok:
                            self.publish_states(mon)
                    elif comp == "brightness":
                        try:
                            val = int(payload)
                            ok, _ = self.mgr.set_vcp(disp_id, 0x10, val)
                            if ok:
                                mon["brightness"] = val
                                self.publish_states(mon)
                        except ValueError:
                            pass
                    elif comp == "contrast":
                        try:
                            val = int(payload)
                            ok, _ = self.mgr.set_vcp(disp_id, 0x12, val)
                            if ok:
                                mon["contrast"] = val
                                self.publish_states(mon)
                        except ValueError:
                            pass
                    elif comp == "volume":
                        try:
                            val = int(payload)
                            ok, _ = self.mgr.set_vcp(disp_id, 0x62, val)
                            if ok:
                                mon["volume"] = val
                                self.publish_states(mon)
                        except ValueError:
                            pass
                    elif comp == "mute":
                        is_on = payload.upper() in ("ON", "1", "TRUE")
                        ok, _ = self.mgr.set_mute(disp_id, is_on)
                        if ok:
                            self.publish_states(mon)
            except Exception as e:
                print(f"[DDC] Error processing MQTT message: {e}", file=sys.stderr)

        try:
            # Instantiate client avoiding Callback API version 1 deprecation warning
            try:
                self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ha_openrgb_ddc_service")
            except (AttributeError, TypeError):
                self.client = mqtt.Client(client_id="ha_openrgb_ddc_service")

            if MQTT_USER and MQTT_PASS:
                print(f"[DDC] Using authenticated MQTT login for user '{MQTT_USER}'")
                self.client.username_pw_set(MQTT_USER, MQTT_PASS)
            else:
                print("[DDC] Connecting to MQTT broker anonymously (no credentials configured)")

            self.client.on_connect = on_connect
            self.client.on_message = on_message
            self.client.connect_async(MQTT_HOST, MQTT_PORT, 60)
            self.client.loop_start()
        except Exception as e:
            print(f"[DDC] Could not connect to MQTT broker: {e}", file=sys.stderr)

    def publish_discovery(self):
        if not self.connected or not self.client:
            return

        for mon in self.mgr.monitors:
            dev_id = mon["device_id"]
            prefix = mon["entity_prefix"]
            mfg = mon["mfg"]
            model = mon["model"]
            device_info = {
                "identifiers": [dev_id],
                "name": mon["device_name"],
                "manufacturer": mfg,
                "model": model,
                "serial_number": mon["serial"],
            }

            # 1. Input Source Select Entity
            # e.g., select.asus_va34vcpsr_monitor_input_source
            input_disc_topic = f"homeassistant/select/{dev_id}_input/config"
            input_config = {
                "name": "Input Source",
                "has_entity_name": True,
                "object_id": f"{prefix}_input_source",
                "unique_id": f"{dev_id}_input_source",
                "device": device_info,
                "icon": "mdi:video-input-hdmi",
                "options": mon["input_options"],
                "state_topic": f"ha_openrgb/ddc/{dev_id}/input/state",
                "command_topic": f"ha_openrgb/ddc/{dev_id}/input/set",
            }
            self.client.publish(input_disc_topic, json.dumps(input_config), retain=True)

            # 2. Brightness Number Entity
            # e.g., number.asus_va34vcpsr_monitor_brightness
            bright_disc_topic = f"homeassistant/number/{dev_id}_brightness/config"
            bright_config = {
                "name": "Brightness",
                "has_entity_name": True,
                "object_id": f"{prefix}_brightness",
                "unique_id": f"{dev_id}_brightness",
                "device": device_info,
                "icon": "mdi:brightness-6",
                "min": 0,
                "max": 100,
                "step": 1,
                "state_topic": f"ha_openrgb/ddc/{dev_id}/brightness/state",
                "command_topic": f"ha_openrgb/ddc/{dev_id}/brightness/set",
            }
            self.client.publish(bright_disc_topic, json.dumps(bright_config), retain=True)

            # 3. Contrast Number Entity
            # e.g., number.asus_va34vcpsr_monitor_contrast
            if mon.get("contrast") is not None:
                contrast_disc_topic = f"homeassistant/number/{dev_id}_contrast/config"
                contrast_config = {
                    "name": "Contrast",
                    "has_entity_name": True,
                    "object_id": f"{prefix}_contrast",
                    "unique_id": f"{dev_id}_contrast",
                    "device": device_info,
                    "icon": "mdi:contrast-circle",
                    "min": 0,
                    "max": 100,
                    "step": 1,
                    "state_topic": f"ha_openrgb/ddc/{dev_id}/contrast/state",
                    "command_topic": f"ha_openrgb/ddc/{dev_id}/contrast/set",
                }
                self.client.publish(contrast_disc_topic, json.dumps(contrast_config), retain=True)

            # 4. Speaker Volume Number Entity
            # e.g., number.asus_va34vcpsr_monitor_speaker_volume
            if mon["has_audio"]:
                vol_disc_topic = f"homeassistant/number/{dev_id}_volume/config"
                vol_config = {
                    "name": "Speaker Volume",
                    "has_entity_name": True,
                    "object_id": f"{prefix}_speaker_volume",
                    "unique_id": f"{dev_id}_volume",
                    "device": device_info,
                    "icon": "mdi:volume-high",
                    "min": 0,
                    "max": 100,
                    "step": 1,
                    "state_topic": f"ha_openrgb/ddc/{dev_id}/volume/state",
                    "command_topic": f"ha_openrgb/ddc/{dev_id}/volume/set",
                }
                self.client.publish(vol_disc_topic, json.dumps(vol_config), retain=True)

            # 5. Audio Mute Switch Entity
            # e.g., switch.asus_va34vcpsr_monitor_audio_mute
            if mon["has_mute"]:
                mute_disc_topic = f"homeassistant/switch/{dev_id}_mute/config"
                mute_config = {
                    "name": "Audio Mute",
                    "has_entity_name": True,
                    "object_id": f"{prefix}_audio_mute",
                    "unique_id": f"{dev_id}_mute",
                    "device": device_info,
                    "icon": "mdi:volume-mute",
                    "payload_on": "ON",
                    "payload_off": "OFF",
                    "state_on": "ON",
                    "state_off": "OFF",
                    "state_topic": f"ha_openrgb/ddc/{dev_id}/mute/state",
                    "command_topic": f"ha_openrgb/ddc/{dev_id}/mute/set",
                }
                self.client.publish(mute_disc_topic, json.dumps(mute_config), retain=True)

            # 6. Quick Switch Buttons for Each Input
            # e.g., button.asus_va34vcpsr_monitor_switch_to_hdmi_1
            for opt in mon["input_options"]:
                clean_opt = clean_identifier(opt)
                btn_disc_topic = f"homeassistant/button/{dev_id}_{clean_opt}/config"
                btn_config = {
                    "name": f"Switch to {opt}",
                    "has_entity_name": True,
                    "object_id": f"{prefix}_switch_to_{clean_opt}",
                    "unique_id": f"{dev_id}_btn_{clean_opt}",
                    "device": device_info,
                    "icon": "mdi:monitor-arrow-down",
                    "command_topic": f"ha_openrgb/ddc/{dev_id}/input/set",
                    "payload_press": opt,
                }
                self.client.publish(btn_disc_topic, json.dumps(btn_config), retain=True)

            # Subscriptions
            self.client.subscribe(f"ha_openrgb/ddc/{dev_id}/input/set")
            self.client.subscribe(f"ha_openrgb/ddc/{dev_id}/brightness/set")
            self.client.subscribe(f"ha_openrgb/ddc/{dev_id}/contrast/set")
            if mon["has_audio"]:
                self.client.subscribe(f"ha_openrgb/ddc/{dev_id}/volume/set")
            if mon["has_mute"]:
                self.client.subscribe(f"ha_openrgb/ddc/{dev_id}/mute/set")

    def publish_states(self, target_mon=None):
        if not self.connected or not self.client:
            return

        monitors = [target_mon] if target_mon else self.mgr.monitors
        for mon in monitors:
            if not mon:
                continue
            dev_id = mon["device_id"]
            if mon.get("current_input_name"):
                self.client.publish(f"ha_openrgb/ddc/{dev_id}/input/state", mon["current_input_name"], retain=True)
            if mon.get("brightness") is not None:
                self.client.publish(f"ha_openrgb/ddc/{dev_id}/brightness/state", str(mon["brightness"]), retain=True)
            if mon.get("contrast") is not None:
                self.client.publish(f"ha_openrgb/ddc/{dev_id}/contrast/state", str(mon["contrast"]), retain=True)
            if mon.get("has_audio") and mon.get("volume") is not None:
                self.client.publish(f"ha_openrgb/ddc/{dev_id}/volume/state", str(mon["volume"]), retain=True)
            if mon.get("has_mute") and mon.get("mute") is not None:
                self.client.publish(f"ha_openrgb/ddc/{dev_id}/mute/state", "ON" if mon["mute"] else "OFF", retain=True)


class DDCRequestHandler(BaseHTTPRequestHandler):
    def send_json(self, status_code, data):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        params = parse_qs(parsed.query)

        if path in ("", "/status", "/displays"):
            self.send_json(200, {
                "status": "ok",
                "monitors_count": len(manager.monitors),
                "monitors": manager.monitors
            })
            return

        disp_id = int(params.get("display", [1])[0])

        if path == "/input":
            target = params.get("to", [None])[0]
            if not target:
                self.send_json(400, {"error": "Missing 'to' parameter (e.g. ?to=HDMI-1 or ?to=0x11)"})
                return
            ok, msg = manager.set_input(disp_id, target)
            if ok:
                mon = next((m for m in manager.monitors if m["display"] == disp_id), None)
                if mqtt_mgr:
                    mqtt_mgr.publish_states(mon)
                self.send_json(200, {"status": "ok", "display": disp_id, "input": mon["current_input_name"] if mon else target})
            else:
                self.send_json(500, {"status": "error", "message": msg})
            return

        if path == "/brightness":
            val = params.get("set", [None])[0]
            if val is None:
                self.send_json(400, {"error": "Missing 'set' parameter (0-100)"})
                return
            try:
                ival = int(val)
                ok, msg = manager.set_vcp(disp_id, 0x10, ival)
                if ok:
                    mon = next((m for m in manager.monitors if m["display"] == disp_id), None)
                    if mon:
                        mon["brightness"] = ival
                    if mqtt_mgr:
                        mqtt_mgr.publish_states(mon)
                    self.send_json(200, {"status": "ok", "display": disp_id, "brightness": ival})
                else:
                    self.send_json(500, {"status": "error", "message": msg})
            except ValueError:
                self.send_json(400, {"error": "Invalid brightness value"})
            return

        if path == "/contrast":
            val = params.get("set", [None])[0]
            if val is None:
                self.send_json(400, {"error": "Missing 'set' parameter (0-100)"})
                return
            try:
                ival = int(val)
                ok, msg = manager.set_vcp(disp_id, 0x12, ival)
                if ok:
                    mon = next((m for m in manager.monitors if m["display"] == disp_id), None)
                    if mon:
                        mon["contrast"] = ival
                    if mqtt_mgr:
                        mqtt_mgr.publish_states(mon)
                    self.send_json(200, {"status": "ok", "display": disp_id, "contrast": ival})
                else:
                    self.send_json(500, {"status": "error", "message": msg})
            except ValueError:
                self.send_json(400, {"error": "Invalid contrast value"})
            return

        if path == "/volume":
            val = params.get("set", [None])[0]
            if val is None:
                self.send_json(400, {"error": "Missing 'set' parameter (0-100)"})
                return
            try:
                ival = int(val)
                ok, msg = manager.set_vcp(disp_id, 0x62, ival)
                if ok:
                    mon = next((m for m in manager.monitors if m["display"] == disp_id), None)
                    if mon:
                        mon["volume"] = ival
                    if mqtt_mgr:
                        mqtt_mgr.publish_states(mon)
                    self.send_json(200, {"status": "ok", "display": disp_id, "volume": ival})
                else:
                    self.send_json(500, {"status": "error", "message": msg})
            except ValueError:
                self.send_json(400, {"error": "Invalid volume value"})
            return

        if path == "/mute":
            val = params.get("set", [None])[0]
            if val is None:
                self.send_json(400, {"error": "Missing 'set' parameter (e.g. ?set=on or ?set=off)"})
                return
            is_on = val.strip().lower() in ("on", "1", "true")
            ok, msg = manager.set_mute(disp_id, is_on)
            if ok:
                mon = next((m for m in manager.monitors if m["display"] == disp_id), None)
                if mqtt_mgr:
                    mqtt_mgr.publish_states(mon)
                self.send_json(200, {"status": "ok", "display": disp_id, "mute": is_on})
            else:
                self.send_json(500, {"status": "error", "message": msg})
            return

        if path == "/power":
            mode = params.get("set", ["on"])[0].strip().lower()
            val = 1
            if mode in ("standby", "2"):
                val = 2
            elif mode in ("suspend", "3"):
                val = 3
            elif mode in ("off", "sleep", "4"):
                val = 4
            elif mode in ("hard_off", "5"):
                val = 5
            ok, msg = manager.set_vcp(disp_id, 0xD6, val)
            if ok:
                self.send_json(200, {"status": "ok", "display": disp_id, "power_mode": mode})
            else:
                self.send_json(500, {"status": "error", "message": msg})
            return

        if path == "/setvcp":
            vcp = params.get("vcp", [None])[0]
            val = params.get("val", [None])[0]
            if not vcp or not val:
                self.send_json(400, {"error": "Missing 'vcp' or 'val' parameter (e.g. ?vcp=60&val=0x11)"})
                return
            ok, msg = manager.set_vcp(disp_id, vcp, val)
            if ok:
                self.send_json(200, {"status": "ok", "display": disp_id, "vcp": vcp, "val": val})
            else:
                self.send_json(500, {"status": "error", "message": msg})
            return

        if path.startswith("/input/"):
            shortcut = path.split("/input/")[1]
            ok, msg = manager.set_input(disp_id, shortcut)
            if ok:
                mon = next((m for m in manager.monitors if m["display"] == disp_id), None)
                if mqtt_mgr:
                    mqtt_mgr.publish_states(mon)
                self.send_json(200, {"status": "ok", "display": disp_id, "input": mon["current_input_name"] if mon else shortcut})
            else:
                self.send_json(500, {"status": "error", "message": msg})
            return

        self.send_json(404, {"error": "Endpoint not found"})

    def log_message(self, format, *args):
        return


mqtt_mgr = None

def poll_loop():
    while True:
        time.sleep(POLL_INTERVAL)
        try:
            for mon in manager.monitors:
                disp_id = mon["display"]
                new_in = manager.get_vcp(disp_id, 0x60)
                if new_in is not None:
                    mon["current_input"] = f"0x{new_in:02x}"
                    mon["current_input_name"] = VESA_INPUT_MAP.get(new_in, f"0x{new_in:02x}")
                new_bright = manager.get_vcp(disp_id, 0x10)
                if new_bright is not None:
                    mon["brightness"] = new_bright
                new_contrast = manager.get_vcp(disp_id, 0x12)
                if new_contrast is not None:
                    mon["contrast"] = new_contrast
                if mon["has_audio"]:
                    new_vol = manager.get_vcp(disp_id, 0x62)
                    if new_vol is not None:
                        mon["volume"] = new_vol
                if mon["has_mute"]:
                    new_mute_val = manager.get_vcp(disp_id, 0x8D)
                    if new_mute_val is not None:
                        mon["mute"] = (new_mute_val == 1)
                if mqtt_mgr:
                    mqtt_mgr.publish_states(mon)
        except Exception as e:
            print(f"[DDC] Poll error: {e}", file=sys.stderr)


def main():
    global mqtt_mgr
    print("[DDC] Initializing Generic DDC/CI Monitor Service...")
    monitors = manager.detect_monitors()
    if not monitors:
        print("[DDC] Note: No DDC-capable monitors detected right now. Will remain active for hotplug/REST.", file=sys.stderr)

    if ENABLE_MQTT:
        mqtt_mgr = MQTTClientManager(manager)
        mqtt_mgr.start()

    poll_thread = threading.Thread(target=poll_loop, daemon=True)
    poll_thread.start()

    server = HTTPServer(("0.0.0.0", DDC_PORT), DDCRequestHandler)
    print(f"[DDC] REST API Server listening on 0.0.0.0:{DDC_PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    print("[DDC] Service stopped.")


if __name__ == "__main__":
    main()
