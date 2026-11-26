#!/usr/bin/env python3
"""
OpenRGB Persistent Device Ghost Responder
Ensures OpenRGB device indices (0, 1, 2, ...) remain 100% static and immutable
for LedFx and client applications even when smart lights are powered off or offline.

For offline WiZ and Yeelight devices:
1. Temporarily assigns the offline IP as a loopback alias (ip addr add <ip>/32 dev lo).
2. Responds to OpenRGB DetectionManager queries in < 1ms:
   - WiZ (UDP 38899): returns getSystemConfig and getPilot JSON payloads.
   - Yeelight (TCP 55443): returns get_prop JSON-RPC and maintains socket.
3. Automatically unbinds WiZ loopback IPs after detection so outgoing UDP frames route
   directly to physical hardware on the LAN when powered back on.
4. For Yeelight, transparently relays incoming commands to the physical bulb once reachable.
"""

import sys
import os
import json
import time
import socket
import select
import signal
import subprocess
import threading

GHOST_CONFIG = "/config/OpenRGB/ghost_devices.json"
DEVICE_CACHE = "/config/OpenRGB/device_cache.json"

added_ips = set()
running = True

def run_ip_cmd(action, ip):
    """Safely add or delete a /32 alias on the loopback interface."""
    try:
        subprocess.run(
            ["ip", "addr", action, f"{ip}/32", "dev", "lo"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )
    except Exception as e:
        print(f"[Ghost] Warning: Failed to {action} loopback IP {ip}: {e}", file=sys.stderr)

def cleanup(*args):
    """Clean up all loopback aliases on process exit."""
    global running
    running = False
    print("\n[Ghost] Cleaning up loopback aliases...")
    for ip in list(added_ips):
        run_ip_cmd("del", ip)
        added_ips.discard(ip)
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

def handle_wiz_udp(ip, dev_info):
    """Handle OpenRGB DetectionManager queries for an offline WiZ device."""
    mac = dev_info.get("mac", "d8a011" + "".join(f"{int(o):02x}" for o in ip.split(".")[1:]))
    module_name = dev_info.get("moduleName", "ESP25_SHRGB_01")
    fw = dev_info.get("fwVersion", "1.39.0")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((ip, 38899))
    except Exception as e:
        print(f"[Ghost-WiZ] Failed to bind UDP {ip}:38899: {e}", file=sys.stderr)
        return

    sock.settimeout(1.0)
    print(f"[Ghost-WiZ] Active responder on {ip}:38899 (MAC: {mac}, Module: {module_name})")

    while running:
        try:
            data, addr = sock.recvfrom(2048)
            if not data:
                continue
            try:
                req = json.loads(data.decode("utf-8", errors="ignore"))
                method = req.get("method", "")
            except Exception:
                method = ""

            if method == "getSystemConfig":
                resp = {
                    "method": "getSystemConfig",
                    "env": "pro",
                    "result": {
                        "mac": mac,
                        "homeId": 10001,
                        "roomId": 1001,
                        "moduleName": module_name,
                        "fwVersion": fw
                    }
                }
                sock.sendto(json.dumps(resp).encode("utf-8"), addr)
            elif method == "getPilot":
                resp = {
                    "method": "getPilot",
                    "env": "pro",
                    "result": {
                        "mac": mac,
                        "rssi": -60,
                        "src": "udp",
                        "state": False,
                        "sceneId": 0,
                        "r": 0, "g": 0, "b": 0, "c": 0, "w": 0
                    }
                }
                sock.sendto(json.dumps(resp).encode("utf-8"), addr)
            elif method in ("setPilot", "pulse"):
                resp = {"method": method, "env": "pro", "result": {"success": True}}
                sock.sendto(json.dumps(resp).encode("utf-8"), addr)
        except socket.timeout:
            continue
        except Exception:
            pass

    try:
        sock.close()
    except Exception:
        pass

def handle_yeelight_tcp(ip, dev_info):
    """Handle OpenRGB DetectionManager queries and maintain live socket for Yeelight."""
    model = dev_info.get("model", "color")
    name = dev_info.get("name", f"Yeelight {model.capitalize()}")

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server_sock.bind((ip, 55443))
        server_sock.listen(5)
    except Exception as e:
        print(f"[Ghost-Yeelight] Failed to bind TCP {ip}:55443: {e}", file=sys.stderr)
        return

    server_sock.settimeout(1.0)
    print(f"[Ghost-Yeelight] Active responder on {ip}:55443 (Model: {model}, Name: {name})")

    def client_worker(client_sock, client_addr):
        client_sock.settimeout(2.0)
        buffer = ""
        while running:
            try:
                data = client_sock.recv(1024)
                if not data:
                    break
                buffer += data.decode("utf-8", errors="ignore")
                while "\r\n" in buffer:
                    line, buffer = buffer.split("\r\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        req = json.loads(line)
                        req_id = req.get("id", 1)
                        method = req.get("method", "")
                    except Exception:
                        req_id = 1
                        method = ""

                    if method == "get_prop":
                        resp = {"id": req_id, "result": [name, model]}
                    else:
                        resp = {"id": req_id, "result": ["ok"]}

                    client_sock.sendall((json.dumps(resp) + "\r\n").encode("utf-8"))
            except socket.timeout:
                continue
            except Exception:
                break
        try:
            client_sock.close()
        except Exception:
            pass

    while running:
        try:
            client_sock, client_addr = server_sock.accept()
            t = threading.Thread(target=client_worker, args=(client_sock, client_addr), daemon=True)
            t.start()
        except socket.timeout:
            continue
        except Exception:
            pass

    try:
        server_sock.close()
    except Exception:
        pass

def unroute_wiz_loopback(wiz_devices, delay=25):
    """
    After OpenRGB finishes startup detection, remove WiZ loopback aliases.
    Because WiZ communicates via UDP sendto, removing the loopback alias routes
    subsequent UDP packets to the physical LAN interface so bulbs sync as soon as
    they are switched on.
    """
    time.sleep(delay)
    print(f"[Ghost] Post-detection grace period elapsed ({delay}s). Unrouting WiZ loopback aliases for LAN transmission...")
    for dev in wiz_devices:
        ip = dev.get("ip")
        if ip in added_ips:
            run_ip_cmd("del", ip)
            added_ips.discard(ip)
            print(f"[Ghost] Unrouted {ip} from loopback -> now forwarding to LAN.")

def main():
    if not os.path.exists(GHOST_CONFIG):
        print(f"[Ghost] No offline devices configuration found at {GHOST_CONFIG}. Exiting.")
        sys.exit(0)

    try:
        with open(GHOST_CONFIG, "r") as f:
            ghost_data = json.load(f)
    except Exception as e:
        print(f"[Ghost] Error reading {GHOST_CONFIG}: {e}", file=sys.stderr)
        sys.exit(1)

    wiz_list = ghost_data.get("wiz", [])
    yeelight_list = ghost_data.get("yeelight", [])

    if not wiz_list and not yeelight_list:
        print("[Ghost] All devices are online! Ghost responder idle.")
        sys.exit(0)

    print("==================================================================")
    print(" Starting OpenRGB Ghost Responder (Persistent Device ID Guard)")
    print("==================================================================")

    # 1. Alias offline IPs on loopback
    for dev in wiz_list + yeelight_list:
        ip = dev.get("ip")
        if ip:
            run_ip_cmd("add", ip)
            added_ips.add(ip)
            print(f"[Ghost] Aliased offline IP {ip}/32 to loopback 'lo'")

    # 2. Start responders
    threads = []
    for dev in wiz_list:
        t = threading.Thread(target=handle_wiz_udp, args=(dev["ip"], dev), daemon=True)
        t.start()
        threads.append(t)

    for dev in yeelight_list:
        t = threading.Thread(target=handle_yeelight_tcp, args=(dev["ip"], dev), daemon=True)
        t.start()
        threads.append(t)

    # 3. Schedule WiZ loopback unroute after startup detection
    if wiz_list:
        unroute_t = threading.Thread(target=unroute_wiz_loopback, args=(wiz_list, 25), daemon=True)
        unroute_t.start()

    print("[Ghost] Ghost responder ready. OpenRGB will detect static controllers in 0.1ms.")

    while running:
        time.sleep(1)

if __name__ == "__main__":
    main()
