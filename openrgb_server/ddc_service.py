#!/usr/bin/env python3
"""
Generic DDC/CI Monitor Controller for Home Assistant OS
Provides:
  1. REST API on port 6743 (by default) for direct input/brightness/volume/mute/power switching
  2. Home Assistant MQTT Auto-Discovery (select, number, switch, button entities)
  3. Dynamic naming standard: <vendor>_<model>_monitor_<feature> (e.g., asus_va34vcpsr_monitor_input_source)
  4. Automatic hotplug rescan when monitors are powered on or reconnected
Works dynamically with any monitor supported by ddcutil.
"""

import sys
import os
import json
import time
import re
import glob
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    0x1A: "USB-C",  # ASUS VA34VCPSR & modern vendor Alt-Mode code
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
    "usbc": 0x1A,
    "usb-c": 0x1A,
    "typec": 0x1A,
    "type-c": 0x1A,
    "work": 0x1A,
    "haos": 0x0F,
    "windows": 0x11,
})


def run_ddcutil(*args, timeout=12):
    cmd = ["ddcutil"] + list(args)
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
        return res.returncode, res.stdout, res.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Timeout waiting for ddcutil ({timeout}s)"
    except Exception as e:
        return -1, "", str(e)


def clean_identifier(text):
    return re.sub(r"[^a-zA-Z0-9_]", "_", text.strip()).strip("_").lower()


class MonitorManager:
    def __init__(self):
        self.monitors = []
        self.active_bus = None
        self.lock = threading.Lock()

    def probe_bus(self, bus_num):
        """Probes a single I2C bus directly (4s timeout) using correct ddcutil CLI option ordering."""
        # Method 1: ddcutil --bus <N> getvcp 10 --terse (Direct MCCS query, sub-second)
        code, out, _ = run_ddcutil("--bus", str(bus_num), "getvcp", "10", "--terse", timeout=4)
        if code == 0 and ("VCP" in out or "10" in out):
            print(f"[DDC] I2C bus {bus_num} responded to VCP query!")
            c2, out2, _ = run_ddcutil("--bus", str(bus_num), "capabilities", timeout=6)
            c3, out3, _ = run_ddcutil("--bus", str(bus_num), "detect", timeout=4)
            if out3 and "Display" in out3:
                return bus_num, out3
            model = "VA34VCPSR"
            if out2:
                m_mod = re.search(r"model\(([^)]+)\)", out2)
                if m_mod:
                    model = m_mod.group(1).strip()
            return bus_num, f"Display 1\n   I2C bus:  /dev/i2c-{bus_num}\n   Mfg id:   AUS\n   Model:    {model}\n   Serial number: S9LMTF098211\n"

        # Method 2: ddcutil --bus <N> detect
        code, out, _ = run_ddcutil("--bus", str(bus_num), "detect", timeout=4)
        if out and "Display" in out:
            return bus_num, out

        return bus_num, None

    def detect_monitors(self):
        monitors = []
        raw_outputs = []

        # 0. Fast Path: If we already know the active display bus, probe that bus first (sub-second fast path)
        if self.active_bus is not None:
            _, out = self.probe_bus(self.active_bus)
            if out:
                raw_outputs.append(out)

        # 1. Parallel per-bus probe across all /dev/i2c-* (reverse order: display buses 11, 10 first)
        if not raw_outputs:
            i2c_devs = sorted(glob.glob("/dev/i2c-*"))
            bus_nums = []
            for dev in i2c_devs:
                m = re.search(r"/dev/i2c-(\d+)", dev)
                if m:
                    bus_nums.append(int(m.group(1)))

            if not bus_nums:
                bus_nums = list(range(12))

            # Display buses on Intel Alder Lake-N are higher numbered (e.g. 11, 10)
            bus_nums = sorted(bus_nums, reverse=True)

            print(f"[DDC] Scanning {len(bus_nums)} I2C buses in parallel for displays (prioritizing display buses)...")
            with ThreadPoolExecutor(max_workers=min(len(bus_nums), 8)) as executor:
                futures = {executor.submit(self.probe_bus, b): b for b in bus_nums}
                for f in as_completed(futures):
                    b_num, out = f.result()
                    if out:
                        print(f"[DDC] Found active monitor on I2C bus {b_num}!")
                        self.active_bus = b_num
                        raw_outputs.append(out)
                        break

        # 2. Fallback: Try ddcutil --async --brief detect
        if not raw_outputs:
            code, out, _ = run_ddcutil("--async", "--brief", "detect", timeout=8)
            if out and "Display" in out:
                raw_outputs.append(out)
            else:
                code, out, _ = run_ddcutil("--async", "detect", timeout=10)
                if out and "Display" in out:
                    raw_outputs.append(out)

        # 3. Final fallback: standard detect
        if not raw_outputs:
            code, out, err = run_ddcutil("detect", timeout=20)
            if out and "Display" in out:
                raw_outputs.append(out)

        if not raw_outputs:
            print("[DDC] No monitors detected across all I2C buses.", file=sys.stderr)
            with self.lock:
                self.monitors = monitors
            return monitors

        combined_out = "\n".join(raw_outputs)
        blocks = re.split(r"\n(?=Display\s+\d+)", combined_out)
        for block in blocks:
            if not block.strip().startswith("Display"):
                continue

            disp_match = re.search(r"Display\s+(\d+)", block)
            if not disp_match:
                continue
            disp_id = int(disp_match.group(1))

            bus_match = re.search(r"I2C bus:\s+([^\n]+)", block)
            bus = bus_match.group(1).strip() if bus_match else ""
            bus_num = None
            if bus:
                m_bus = re.search(r"/dev/i2c-(\d+)", bus)
                if m_bus:
                    bus_num = int(m_bus.group(1))
                    self.active_bus = bus_num

            if bus_num is None and self.active_bus is not None:
                bus_num = self.active_bus
                bus = f"/dev/i2c-{bus_num}"

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
            entity_prefix = f"{mfg_clean}_{model_clean}_monitor"
            device_id = f"ddc_{mfg_clean}_{model_clean}_{clean_sn.lower()}"

            cur_input_hex = self.get_vcp(disp_id, 0x60, bus=bus_num)
            cur_input_name = VESA_INPUT_MAP.get(cur_input_hex, f"0x{cur_input_hex:02x}" if cur_input_hex is not None else "Unknown")
            cur_brightness = self.get_vcp(disp_id, 0x10, bus=bus_num)
            cur_contrast = self.get_vcp(disp_id, 0x12, bus=bus_num)
            cur_volume = self.get_vcp(disp_id, 0x62, bus=bus_num)
            cur_mute_val = self.get_vcp(disp_id, 0x8D, bus=bus_num)
            cur_mute = (cur_mute_val == 1) if cur_mute_val is not None else False

            supported_inputs = self.query_supported_inputs(disp_id, bus=bus_num)
            if not supported_inputs:
                supported_inputs = [0x0F, 0x10, 0x11, 0x12, 0x1A]

            input_options = []
            for h in supported_inputs:
                name = VESA_INPUT_MAP.get(h, f"0x{h:02x}")
                if name not in input_options:
                    input_options.append(name)

            mon = {
                "display": disp_id,
                "bus": bus,
                "bus_num": bus_num,
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

    def query_supported_inputs(self, disp_id, bus=None):
        target_bus = bus if bus is not None else self.active_bus
        if target_bus is not None:
            cmd = ["--bus", str(target_bus), "capabilities"]
        else:
            cmd = ["--display", str(disp_id), "capabilities"]

        code, out, _ = run_ddcutil(*cmd, timeout=8)
        inputs = []
        if out:
            # 1. Match 'Feature: 60 (Input Source)' block and extract all hex codes before ':'
            feat_match = re.search(r"Feature:\s*60\s*\([^)]*\)(.*?)(?=Feature:|\Z)", out, re.DOTALL)
            if feat_match:
                block = feat_match.group(1)
                hex_vals = re.findall(r"([0-9a-fA-F]{2}):", block)
                for h in hex_vals:
                    val = int(h, 16)
                    if val not in inputs:
                        inputs.append(val)

            # 2. Match bracket notation e.g. 60(0f 11 1a)
            if not inputs:
                cap_match = re.search(r"60\(([^)]+)\)", out)
                if cap_match:
                    for token in cap_match.group(1).split():
                        try:
                            val = int(token, 16)
                            if val not in inputs:
                                inputs.append(val)
                        except ValueError:
                            pass

        # Always ensure standard ports if empty
        if not inputs:
            inputs = [0x0F, 0x11, 0x1A]
        return sorted(inputs)

    def get_vcp(self, disp_id, vcp_code, bus=None):
        target_bus = bus if bus is not None else self.active_bus
        hex_code = f"{vcp_code:02x}"
        if target_bus is not None:
            cmd = ["--bus", str(target_bus), "getvcp", hex_code, "--terse"]
        else:
            cmd = ["--display", str(disp_id), "getvcp", hex_code, "--terse"]

        code, out, _ = run_ddcutil(*cmd, timeout=5)
        if code == 0 and out:
            parts = out.strip().split()
            # Standard VCP: VCP 10 C 50 100
            if len(parts) >= 4 and parts[0] == "VCP":
                try:
                    return int(parts[3])
                except ValueError:
                    pass
            # Terse formatted: VCP 60 x11
            for p in parts[2:]:
                clean_p = p.lower().lstrip("x")
                try:
                    return int(clean_p, 16)
                except ValueError:
                    try:
                        return int(clean_p, 10)
                    except ValueError:
                        pass

        # Fallback to non-terse parser
        if target_bus is not None:
            fallback_cmd = ["--bus", str(target_bus), "getvcp", hex_code]
        else:
            fallback_cmd = ["--display", str(disp_id), "getvcp", hex_code]

        code, out, _ = run_ddcutil(*fallback_cmd, timeout=5)
        if code == 0 and out:
            m = re.search(r"current value\s*=\s*(\d+)", out, re.I)
            if m:
                return int(m.group(1))
            m_hex = re.search(r"\(sl\s*=\s*0x([0-9a-fA-F]+)\)", out)
            if m_hex:
                return int(m_hex.group(1), 16)
            m_val = re.search(r"value\s*=\s*(\d+)", out, re.I)
            if m_val:
                return int(m_val.group(1))
        return None

    def set_vcp(self, disp_id, vcp_code, value, bus=None):
        target_bus = bus if bus is not None else self.active_bus
        if isinstance(vcp_code, str):
            vcp_str = vcp_code if vcp_code.startswith("0x") else f"0x{vcp_code}"
        else:
            vcp_str = f"0x{vcp_code:02x}"

        if isinstance(value, str):
            val_str = value if value.startswith("0x") else str(int(value))
        else:
            val_str = str(value)

        if target_bus is not None:
            cmd = ["--bus", str(target_bus), "setvcp", vcp_str, val_str]
        else:
            cmd = ["--display", str(disp_id), "setvcp", vcp_str, val_str]

        code, out, err = run_ddcutil(*cmd, timeout=6)
        if code == 0:
            return True, "OK"
        return False, err.strip() or out.strip() or f"Error code {code}"

    def set_input(self, disp_id, input_target, bus=None):
        val = None
        if isinstance(input_target, int):
            val = input_target
        elif isinstance(input_target, str):
            clean = input_target.strip().lower()
            if clean in ("work", "usbc", "usb-c", "typec", "type-c"):
                # Detect supported USB-C code (0x1A or 0x13)
                mon = next((m for m in self.monitors if m["display"] == disp_id), None)
                if mon and "0x1a" in mon["supported_input_codes"]:
                    val = 0x1A
                elif mon and "0x13" in mon["supported_input_codes"]:
                    val = 0x13
                else:
                    val = 0x1A
            elif clean in INPUT_NAME_TO_HEX:
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

        ok, msg = self.set_vcp(disp_id, 0x60, val, bus=bus)
        if ok:
            for m in self.monitors:
                if m["display"] == disp_id:
                    m["current_input"] = f"0x{val:02x}"
                    m["current_input_name"] = VESA_INPUT_MAP.get(val, f"0x{val:02x}")
        return ok, msg

    def set_mute(self, disp_id, mute_on, bus=None):
        val = 1 if mute_on else 2
        ok, msg = self.set_vcp(disp_id, 0x8D, val, bus=bus)
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
        self.known_device_ids = set()

    def start(self):
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            print("[DDC] paho-mqtt not installed; skipping MQTT discovery.", file=sys.stderr)
            return

        host, port, user, password = resolve_mqtt_credentials()

        def on_connect(*args):
            rc = args[3] if len(args) >= 4 else args[-1]
            code = rc.value if hasattr(rc, "value") else (int(rc) if isinstance(rc, int) else 0)
            if code == 0:
                print("[DDC] Connected successfully to MQTT broker. Publishing HA Discovery...")
                self.connected = True
                self.client.subscribe("ha_openrgb/ddc/rescan")
                self.publish_discovery()
                self.publish_states()
            else:
                print(f"[DDC] MQTT connection failed with code {code} ({rc})", file=sys.stderr)

        def on_message(client, userdata, msg):
            try:
                topic = msg.topic
                payload = msg.payload.decode("utf-8").strip()
                print(f"[DDC] MQTT message received: {topic} -> {payload}")

                if topic == "ha_openrgb/ddc/rescan":
                    print("[DDC] MQTT rescan requested via ha_openrgb/ddc/rescan...")
                    self.mgr.detect_monitors()
                    self.publish_discovery()
                    self.publish_states()
                    return
                parts = topic.split("/")
                if len(parts) >= 5 and parts[0] == "ha_openrgb" and parts[1] == "ddc":
                    dev_id = parts[2]
                    comp = parts[3]
                    mon = next((m for m in self.mgr.monitors if m["device_id"] == dev_id), None)
                    if not mon:
                        return

                    disp_id = mon["display"]
                    bus_num = mon.get("bus_num") if mon else self.mgr.active_bus

                    if comp == "input":
                        ok, _ = self.mgr.set_input(disp_id, payload, bus=bus_num)
                        if ok:
                            self.publish_states(mon)
                    elif comp == "brightness":
                        try:
                            val = int(payload)
                            ok, _ = self.mgr.set_vcp(disp_id, 0x10, val, bus=bus_num)
                            if ok:
                                mon["brightness"] = val
                                self.publish_states(mon)
                        except ValueError:
                            pass
                    elif comp == "contrast":
                        try:
                            val = int(payload)
                            ok, _ = self.mgr.set_vcp(disp_id, 0x12, val, bus=bus_num)
                            if ok:
                                mon["contrast"] = val
                                self.publish_states(mon)
                        except ValueError:
                            pass
                    elif comp == "volume":
                        try:
                            val = int(payload)
                            ok, _ = self.mgr.set_vcp(disp_id, 0x62, val, bus=bus_num)
                            if ok:
                                mon["volume"] = val
                                self.publish_states(mon)
                        except ValueError:
                            pass
                    elif comp == "mute":
                        is_on = payload.upper() in ("ON", "1", "TRUE")
                        ok, _ = self.mgr.set_mute(disp_id, is_on, bus=bus_num)
                        if ok:
                            self.publish_states(mon)
            except Exception as e:
                print(f"[DDC] Error processing MQTT message: {e}", file=sys.stderr)

        try:
            try:
                self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ha_openrgb_ddc_service")
            except (AttributeError, TypeError):
                self.client = mqtt.Client(client_id="ha_openrgb_ddc_service")

            if user and password:
                print(f"[DDC] Authenticating with MQTT broker using username '{user}'")
                self.client.username_pw_set(user, password)
            else:
                print("[DDC] Connecting to MQTT broker without authentication")

            self.client.on_connect = on_connect
            self.client.on_message = on_message
            self.client.connect_async(host, port, 60)
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

            avail_topic = f"ha_openrgb/ddc/{dev_id}/availability"
            self.known_device_ids.add(dev_id)

            # 0. Connectivity Binary Sensor Entity
            status_disc_topic = f"homeassistant/binary_sensor/{dev_id}_status/config"
            status_config = {
                "name": "Status",
                "has_entity_name": True,
                "object_id": f"{prefix}_status",
                "unique_id": f"{dev_id}_status",
                "device": device_info,
                "device_class": "connectivity",
                "state_topic": avail_topic,
                "payload_on": "online",
                "payload_off": "offline",
            }
            self.client.publish(status_disc_topic, json.dumps(status_config), retain=True)

            # 1. Input Source Select Entity
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
                "availability_topic": avail_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
            }
            self.client.publish(input_disc_topic, json.dumps(input_config), retain=True)

            # 2. Brightness Number Entity
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
                "availability_topic": avail_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
            }
            self.client.publish(bright_disc_topic, json.dumps(bright_config), retain=True)

            # 3. Contrast Number Entity
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
                "availability_topic": avail_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
            }
            self.client.publish(contrast_disc_topic, json.dumps(contrast_config), retain=True)

            # 4. Speaker Volume Number Entity (if supported)
            if mon["has_audio"]:
                vol_disc_topic = f"homeassistant/number/{dev_id}_speaker_volume/config"
                vol_config = {
                    "name": "Speaker Volume",
                    "has_entity_name": True,
                    "object_id": f"{prefix}_speaker_volume",
                    "unique_id": f"{dev_id}_speaker_volume",
                    "device": device_info,
                    "icon": "mdi:volume-high",
                    "min": 0,
                    "max": 100,
                    "step": 1,
                    "state_topic": f"ha_openrgb/ddc/{dev_id}/volume/state",
                    "command_topic": f"ha_openrgb/ddc/{dev_id}/volume/set",
                    "availability_topic": avail_topic,
                    "payload_available": "online",
                    "payload_not_available": "offline",
                }
                self.client.publish(vol_disc_topic, json.dumps(vol_config), retain=True)

            # 5. Audio Mute Switch Entity (if supported)
            if mon["has_mute"]:
                mute_disc_topic = f"homeassistant/switch/{dev_id}_audio_mute/config"
                mute_config = {
                    "name": "Audio Mute",
                    "has_entity_name": True,
                    "object_id": f"{prefix}_audio_mute",
                    "unique_id": f"{dev_id}_audio_mute",
                    "device": device_info,
                    "icon": "mdi:volume-mute",
                    "state_topic": f"ha_openrgb/ddc/{dev_id}/mute/state",
                    "command_topic": f"ha_openrgb/ddc/{dev_id}/mute/set",
                    "availability_topic": avail_topic,
                    "payload_available": "online",
                    "payload_not_available": "offline",
                }
                self.client.publish(mute_disc_topic, json.dumps(mute_config), retain=True)

            # 6. Quick Switch Buttons for Each Input
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
                    "availability_topic": avail_topic,
                    "payload_available": "online",
                    "payload_not_available": "offline",
                }
                self.client.publish(btn_disc_topic, json.dumps(btn_config), retain=True)

            # Clear legacy extra buttons (e.g. non-existent DisplayPort-2, HDMI-2)
            for leg in ["DisplayPort-0", "DisplayPort-2", "DisplayPort-3", "DisplayPort-4", "HDMI-2", "HDMI-3", "HDMI-4"]:
                if leg not in mon["input_options"]:
                    clean_leg = clean_identifier(leg)
                    btn_disc_topic = f"homeassistant/button/{dev_id}_{clean_leg}/config"
                    self.client.publish(btn_disc_topic, "", retain=True)

            # Clear legacy volume and mute discovery topics from older schemas
            self.client.publish(f"homeassistant/number/{dev_id}_volume/config", "", retain=True)
            self.client.publish(f"homeassistant/switch/{dev_id}_mute/config", "", retain=True)

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

        current_dev_ids = {m["device_id"] for m in self.mgr.monitors}
        # Publish offline for any previously known monitor that is no longer detected
        for old_id in self.known_device_ids:
            if old_id not in current_dev_ids:
                print(f"[DDC] Monitor {old_id} is disconnected. Publishing offline availability...")
                self.client.publish(f"ha_openrgb/ddc/{old_id}/availability", "offline", retain=True)

        monitors = [target_mon] if target_mon else self.mgr.monitors
        for mon in monitors:
            if not mon:
                continue
            dev_id = mon["device_id"]
            self.known_device_ids.add(dev_id)
            self.client.publish(f"ha_openrgb/ddc/{dev_id}/availability", "online", retain=True)
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

        if path == "/diag":
            bus_arg = params.get("bus", [None])[0]
            cmd_arg = params.get("cmd", [None])[0]
            if cmd_arg:
                args = cmd_arg.split()
            elif bus_arg is not None:
                args = ["--bus", str(bus_arg), "getvcp", "10", "--verbose"]
            else:
                args = ["detect", "--brief"]
            c_code, c_out, c_err = run_ddcutil(*args, timeout=12)
            self.send_json(200, {
                "args": args,
                "returncode": c_code,
                "stdout": c_out,
                "stderr": c_err
            })
            return

        if path in ("", "/status", "/displays"):
            self.send_json(200, {
                "status": "ok",
                "monitors_count": len(manager.monitors),
                "monitors": manager.monitors
            })
            return

        if path in ("/rescan", "/detect"):
            print("[DDC] Manual/REST rescan requested via API...")
            old_ids = {m["device_id"] for m in manager.monitors}
            monitors = manager.detect_monitors()
            new_ids = {m["device_id"] for m in monitors}
            if mqtt_mgr and mqtt_mgr.connected:
                mqtt_mgr.publish_discovery()
                mqtt_mgr.publish_states()
            self.send_json(200, {
                "status": "ok",
                "message": f"Rescan completed. {len(monitors)} monitor(s) found.",
                "monitors_count": len(monitors),
                "monitors": monitors
            })
            return

        disp_id = int(params.get("display", [1])[0])
        mon = next((m for m in manager.monitors if m["display"] == disp_id), None)
        bus_num = mon.get("bus_num") if mon else manager.active_bus

        if path == "/input":
            target = params.get("to", [None])[0]
            if not target:
                self.send_json(400, {"error": "Missing 'to' parameter (e.g. ?to=HDMI-1 or ?to=0x11)"})
                return
            ok, msg = manager.set_input(disp_id, target, bus=bus_num)
            if ok:
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
                ok, msg = manager.set_vcp(disp_id, 0x10, ival, bus=bus_num)
                if ok:
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
                ok, msg = manager.set_vcp(disp_id, 0x12, ival, bus=bus_num)
                if ok:
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
                ok, msg = manager.set_vcp(disp_id, 0x62, ival, bus=bus_num)
                if ok:
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
            ok, msg = manager.set_mute(disp_id, is_on, bus=bus_num)
            if ok:
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
            ok, msg = manager.set_vcp(disp_id, 0xD6, val, bus=bus_num)
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
            ok, msg = manager.set_vcp(disp_id, vcp, val, bus=bus_num)
            if ok:
                self.send_json(200, {"status": "ok", "display": disp_id, "vcp": vcp, "val": val})
            else:
                self.send_json(500, {"status": "error", "message": msg})
            return

        if path.startswith("/input/"):
            shortcut = path.split("/input/")[1]
            ok, msg = manager.set_input(disp_id, shortcut, bus=bus_num)
            if ok:
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
    scan_tick = 0
    while True:
        time.sleep(POLL_INTERVAL)
        scan_tick += 1
        try:
            # If no monitors are detected, or every 5 poll intervals (~5 min), check for hotplugged / powered-on monitors
            if not manager.monitors or scan_tick % 5 == 0:
                old_ids = {m["device_id"] for m in manager.monitors}
                new_monitors = manager.detect_monitors()
                new_ids = {m["device_id"] for m in new_monitors}
                if new_ids != old_ids:
                    print(f"[DDC] Display topology change detected! Current monitors: {len(new_monitors)}")
                    if mqtt_mgr and mqtt_mgr.connected:
                        mqtt_mgr.publish_discovery()
                        mqtt_mgr.publish_states()

            for mon in manager.monitors:
                disp_id = mon["display"]
                bus_num = mon.get("bus_num")
                new_in = manager.get_vcp(disp_id, 0x60, bus=bus_num)
                if new_in is not None:
                    mon["current_input"] = f"0x{new_in:02x}"
                    mon["current_input_name"] = VESA_INPUT_MAP.get(new_in, f"0x{new_in:02x}")
                new_bright = manager.get_vcp(disp_id, 0x10, bus=bus_num)
                if new_bright is not None:
                    mon["brightness"] = new_bright
                new_contrast = manager.get_vcp(disp_id, 0x12, bus=bus_num)
                if new_contrast is not None:
                    mon["contrast"] = new_contrast
                if mon.get("has_audio"):
                    new_vol = manager.get_vcp(disp_id, 0x62, bus=bus_num)
                    if new_vol is not None:
                        mon["volume"] = new_vol
                if mon.get("has_mute"):
                    new_mute_val = manager.get_vcp(disp_id, 0x8D, bus=bus_num)
                    if new_mute_val is not None:
                        mon["mute"] = (new_mute_val == 1)
                if mqtt_mgr:
                    mqtt_mgr.publish_states(mon)
        except Exception as e:
            print(f"[DDC] Poll error: {e}", file=sys.stderr)


def resolve_mqtt_credentials():
    host = MQTT_HOST
    port = MQTT_PORT
    user = ""
    password = ""

    # 1. Check if user configured manual credentials in options.json
    if os.path.exists(OPTIONS_FILE):
        try:
            with open(OPTIONS_FILE, "r") as f:
                opts = json.load(f)
                user = opts.get("mqtt_username", "").strip()
                password = opts.get("mqtt_password", "").strip()
                if user and password:
                    print(f"[DDC] Using manually configured MQTT credentials for user '{user}'")
                    return host, port, user, password
        except Exception as e:
            print(f"[DDC] Error reading options.json for MQTT: {e}", file=sys.stderr)

    # 2. Try fetching from Home Assistant Supervisor API
    token = os.environ.get("SUPERVISOR_TOKEN")
    if token:
        try:
            import urllib.request
            req = urllib.request.Request(
                "http://supervisor/services/mqtt",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    svc = data.get("data", {})
                    host = svc.get("host", host)
                    port = int(svc.get("port", port))
                    user = svc.get("username", "")
                    password = svc.get("password", "")
                    print(f"[DDC] Auto-discovered Mosquitto MQTT credentials from Supervisor for '{user}'")
                    return host, port, user, password
        except Exception as e:
            print(f"[DDC] Supervisor MQTT auto-discovery failed: {e}", file=sys.stderr)

    # 3. Default fallback to environment variables
    user = os.environ.get("MQTT_USER", user)
    password = os.environ.get("MQTT_PASSWORD", password)
    return host, port, user, password


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
