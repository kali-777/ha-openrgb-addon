# OpenRGB SDK Server Add-on Documentation

## Overview
This add-on runs a headless **OpenRGB SDK Server (`v1.0+`)** directly inside Home Assistant OS (HAOS).

It solves three major problems for Smart Home & Audio-Reactive Lighting setups:
1. **Direct USB RGB Peripherals on HAOS:** Control USB RGB devices plugged directly into your Home Assistant server (e.g., **HyperX DuoCast** / **QuadCast S** USB Microphones, Razer Chroma accessories, USB ARGB controllers).
2. **Always-On Wi-Fi Smart Light Bridging for LedFx:** Bridges **Philips WiZ**, **Xiaomi Yeelight**, and **TP-Link Kasa** lights to **LedFx** via the OpenRGB SDK protocol (`port 6742`) 24/7 — even when your desktop PC or ARM64 laptop is turned off!
3. **Automatic `OPENRGB ID` Discovery in Logs:** On startup, the add-on enumerates all USB and Network RGB devices and prints their exact `Device Index (OPENRGB ID)` and `LED Count` in the **Log** tab.

---

## Configuration Options

| Option | Default | Description |
| :--- | :--- | :--- |
| `server_port` | `6742` | TCP port for the OpenRGB SDK Server. |
| `server_host` | `0.0.0.0` | Listen address (`0.0.0.0` listens on `127.0.0.1` and LAN IP). |
| `list_devices_on_start` | `true` | Prints all detected `OPENRGB ID` numbers (`0, 1, 2...`) in the Add-on Log on startup. |
| `wiz_ips` | `["192.168.2.65"]` | List of Philips WiZ static IP addresses. |
| `wiz_white_strategy` | `"Average"` | White LED calculation mode for WiZ lights (`Average`, `Lowest`, `None`). |
| `yeelight_ips` | `[]` | List of Xiaomi Yeelight static IP addresses (requires **LAN Control** enabled in Yeelight app). |
| `yeelight_music_mode` | `true` | Enables low-latency TCP Music Mode for Yeelight strips/lamps. |
| `kasa_ips` | `[]` | List of TP-Link Kasa smart light IP addresses. |
| `extra_args` | `""` | Additional CLI flags passed to `openrgb`. |

---

## Connecting to LedFx & Home Assistant

### 1. Connecting the LedFx Add-on (Running on the Same HAOS Host)
1. Start this **OpenRGB SDK Server** add-on and check the **Log** tab to see your device IDs:
   - e.g. `0: HyperX DuoCast` (2 LEDs)
   - e.g. `1: Philips Wiz` (1 LED)
2. Open the **LedFx Web UI** → **Add Device** → select **`openrgb`**:
   - **IP Address:** `127.0.0.1` (or your HAOS LAN IP `192.168.2.20`)
   - **Port:** `6742`
   - **OpenRGB ID:** `0` (or `1`, etc.)
   - **Pixel Count:** Match the LED count shown in the log (`2` for HyperX DuoCast, `1` for WiZ/Yeelight).

### 2. Connecting Home Assistant's Native OpenRGB Integration
1. Go to **Settings → Devices & Services → Add Integration → OpenRGB**.
2. Enter Host: `127.0.0.1` and Port: `6742`.
3. All USB and Wi-Fi devices hosted by this add-on will appear as native `light.*` entities in Home Assistant!
