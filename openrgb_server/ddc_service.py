#!/usr/bin/env python3
"""
Generic DDC/CI Monitor Controller for Home Assistant OS
Provides:
  1. REST API on port 6743 (by default) for direct input/brightness/volume/power switching
  2. Home Assistant MQTT Auto-Discovery (select, number, button entities)
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
DDC_PORT = 6743
MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883
POLL_INTERVAL = 60
ENABLE_MQTT = True

if os.path.exists(OPTIONS_FILE):
    try:
        with open(OPTIONS_FILE, "r") as f:
            opts = json.load(f)
            DDC_PORT = int(opts.get("ddc_port", 6743))
            ENABLE_MQTT = bool(opts.get("ddc_mqtt_discovery", True))
            POLL_INTERVAL = int(opts.get("ddc_poll_interval", 60))
    except Exception as e:
        print(f"[DDC] Error loading options.json: {e}", file=sys.stderr)

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


class MonitorManager:
    def __init__(self):
        self.monitors = []
        self.lock = threading.Lock()

    def detect_monitors(self):
        code, out, err = run_ddcutil("detect")
        monitors = []
        if code != 0 or not out:
            print(f"[DDC] No monitors detected or error: {err}", file=sys.stderr)
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
            mfg = mfg_match.group(1).strip() if mfg_match else "Generic"

            model_match = re.search(r"Model:\s+([^\n]+)", block)
            model = model_match.group(1).strip() if model_match else f"Monitor_{disp_id}"

            sn_match = re.search(r"Serial number:\s+([^\n]+)", block)
            sn = sn_match.group(1).strip() if sn_match else f"disp{disp_id}"
            clean_sn = re.sub(r"[^A-Za-z0-9_-]", "_", sn)

            cur_input_hex = self.get_vcp(disp_id, 0x60)
            cur_input_name = VESA_INPUT_MAP.get(cur_input_hex, f"0x{cur_input_hex:02x}" if cur_input_hex is not None else "Unknown")
            cur_brightness = self.get_vcp(disp_id, 0x10)
            cur_volume = self.get_vcp(disp_id, 0x62)

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
                "current_input": f"0x{cur_input_hex:02x}" if cur_input_hex is not None else None,
                "current_input_name": cur_input_name,
                "supported_input_codes": [f"0x{h:02x}" for h in supported_inputs],
                "input_options": input_options,
                "brightness": cur_brightness,
                "volume": cur_volume,
                "has_audio": (cur_volume is not None),
            }
            monitors.append(mon)
            print(f"[DDC] Discovered: Display {disp_id} - {mfg} {model} (SN: {clean_sn}) on {bus}")
            print(f"[DDC]   Current Input: {cur_input_name} | Supported: {', '.join(input_options)}")

        with self.lock:
            self.monitors = monitors
        return monitors

    def query_supported_inputs(self, disp_id):
        code, out, _ = run_ddcutil("--display", str(disp_id), "capabilities")
        inputs = []
        if code == 0 and out:
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
        if code == 0 and out:
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

        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                print("[DDC] Connected to MQTT broker. Publishing HA Discovery...")
                self.connected = True
                self.publish_discovery()
                self.publish_states()
            else:
                print(f"[DDC] MQTT connection failed with code {rc}", file=sys.stderr)

        def on_message(client, userdata, msg):
            try:
                topic = msg.topic
                payload = msg.payload.decode("utf-8").strip()
                print(f"[DDC] MQTT message received: {topic} -> {payload}")

                parts = topic.split("/")
                if len(parts) >= 5 and parts[0] == "ha_openrgb" and parts[1] == "ddc":
                    serial = parts[2]
                    comp = parts[3]
                    mon = next((m for m in self.mgr.monitors if m["serial"] == serial), None)
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
                    elif comp == "volume":
                        try:
                            val = int(payload)
                            ok, _ = self.mgr.set_vcp(disp_id, 0x62, val)
                            if ok:
                                mon["volume"] = val
                                self.publish_states(mon)
                        except ValueError:
                            pass
            except Exception as e:
                print(f"[DDC] Error processing MQTT message: {e}", file=sys.stderr)

        try:
            self.client = mqtt.Client(client_id="ha_openrgb_ddc_service")
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
            sn = mon["serial"]
            mfg = mon["mfg"]
            model = mon["model"]
            device_info = {
                "identifiers": [f"ddc_{sn}"],
                "name": f"{mfg} {model}",
                "manufacturer": mfg,
                "model": model,
                "serial_number": sn,
            }

            input_disc_topic = f"homeassistant/select/ddc_{sn}_input/config"
            input_config = {
                "name": "Input Source",
                "unique_id": f"ddc_{sn}_input_source",
                "device": device_info,
                "icon": "mdi:video-input-hdmi",
                "options": mon["input_options"],
                "state_topic": f"ha_openrgb/ddc/{sn}/input/state",
                "command_topic": f"ha_openrgb/ddc/{sn}/input/set",
            }
            self.client.publish(input_disc_topic, json.dumps(input_config), retain=True)

            bright_disc_topic = f"homeassistant/number/ddc_{sn}_brightness/config"
            bright_config = {
                "name": "Brightness",
                "unique_id": f"ddc_{sn}_brightness",
                "device": device_info,
                "icon": "mdi:brightness-6",
                "min": 0,
                "max": 100,
                "step": 1,
                "state_topic": f"ha_openrgb/ddc/{sn}/brightness/state",
                "command_topic": f"ha_openrgb/ddc/{sn}/brightness/set",
            }
            self.client.publish(bright_disc_topic, json.dumps(bright_config), retain=True)

            if mon["has_audio"]:
                vol_disc_topic = f"homeassistant/number/ddc_{sn}_volume/config"
                vol_config = {
                    "name": "Speaker Volume",
                    "unique_id": f"ddc_{sn}_volume",
                    "device": device_info,
                    "icon": "mdi:volume-high",
                    "min": 0,
                    "max": 100,
                    "step": 1,
                    "state_topic": f"ha_openrgb/ddc/{sn}/volume/state",
                    "command_topic": f"ha_openrgb/ddc/{sn}/volume/set",
                }
                self.client.publish(vol_disc_topic, json.dumps(vol_config), retain=True)

            for opt in mon["input_options"]:
                clean_opt = re.sub(r"[^a-zA-Z0-9_]", "_", opt.lower())
                btn_disc_topic = f"homeassistant/button/ddc_{sn}_{clean_opt}/config"
                btn_config = {
                    "name": f"Switch to {opt}",
                    "unique_id": f"ddc_{sn}_btn_{clean_opt}",
                    "device": device_info,
                    "icon": "mdi:monitor-arrow-down",
                    "command_topic": f"ha_openrgb/ddc/{sn}/input/set",
                    "payload_press": opt,
                }
                self.client.publish(btn_disc_topic, json.dumps(btn_config), retain=True)

            self.client.subscribe(f"ha_openrgb/ddc/{sn}/input/set")
            self.client.subscribe(f"ha_openrgb/ddc/{sn}/brightness/set")
            if mon["has_audio"]:
                self.client.subscribe(f"ha_openrgb/ddc/{sn}/volume/set")

    def publish_states(self, target_mon=None):
        if not self.connected or not self.client:
            return

        monitors = [target_mon] if target_mon else self.mgr.monitors
        for mon in monitors:
            if not mon:
                continue
            sn = mon["serial"]
            if mon.get("current_input_name"):
                self.client.publish(f"ha_openrgb/ddc/{sn}/input/state", mon["current_input_name"], retain=True)
            if mon.get("brightness") is not None:
                self.client.publish(f"ha_openrgb/ddc/{sn}/brightness/state", str(mon["brightness"]), retain=True)
            if mon.get("has_audio") and mon.get("volume") is not None:
                self.client.publish(f"ha_openrgb/ddc/{sn}/volume/state", str(mon["volume"]), retain=True)


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
                if mon["has_audio"]:
                    new_vol = manager.get_vcp(disp_id, 0x62)
                    if new_vol is not None:
                        mon["volume"] = new_vol
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
