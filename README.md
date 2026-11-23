# Home Assistant Add-on: OpenRGB SDK Server & DDC/CI Monitor Control (`v1.1.8`)

[![Open your Home Assistant instance and show the add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fkali-777%2Fha-openrgb-addon)

Run a headless **OpenRGB SDK Server (`v1.0+`)** and **Generic DDC/CI Hardware Monitor Controller** directly on **Home Assistant OS (HAOS)** (`amd64` / `aarch64` / `armv7`).

Designed to provide two essential capabilities in a single unified daemon:
1. **Generic DDC/CI Monitor Control via `/dev/i2c-*`**: Hardware input source switching (`HDMI-1`, `USB-C`, `DisplayPort-1`), hardware speaker volume (`VCP 0x62`), mute (`VCP 0x8D`), brightness (`VCP 0x10`), and contrast (`VCP 0x12`) with automatic Home Assistant MQTT Discovery (`select`, `number`, `switch`, `button` entities named `<vendor>_<model>_monitor_*`) and an embedded REST API (`port 6743`).
2. **RGB Hardware & Smart Light Bridging for LedFx**: Bridge direct USB RGB peripherals (HyperX DuoCast/QuadCast microphones, Razer keyboards) and Wi-Fi smart lights (Philips WiZ, Xiaomi Yeelight, TP-Link Kasa) to LedFx and Home Assistant 24/7 without needing your desktop PC turned on.

---

## Critical Prerequisites

### 1. Disable Protection Mode (Unprotected Mode) for DDC/CI Monitor Control

> [!WARNING]
> **Protection Mode must be toggled OFF ("Unprotected mode"):**
> To allow `ddcutil` to communicate directly with computer monitors over motherboard Linux I2C buses (`/dev/i2c-*`), Home Assistant OS requires the container to run without AppArmor confinement:
> 1. In Home Assistant, navigate to **Settings → Add-ons → OpenRGB SDK Server**.
> 2. On the **Info** tab, toggle **Protection mode** to **OFF** (Disabled).
> 3. Restart the add-on.
> *(If Protection mode remains enabled, accessing `/dev/i2c-*` results in Linux error `EPERM: Operation not permitted` and monitors cannot be detected or controlled).*

### 2. Static / Fixed IP Reservations for Smart Lights

> [!IMPORTANT]
> **Static / Fixed IP DHCP Reservations Required:**
> OpenRGB connects directly to Wi-Fi network smart lights over raw TCP/UDP sockets by IP address.
> - **Assign Fixed IPs:** You **must** configure static DHCP IP reservations in your Wi-Fi router or gateway (e.g., TP-Link Omada, ER605, UniFi, ASUS, etc.) for each smart light (`wiz_ips`, `yeelight_ips`, `kasa_ips`). If a light gets a new dynamic IP after a router reboot, OpenRGB will lose connection to it.
> - **Xiaomi Yeelight LAN Control:** For Yeelight bulbs and light strips, open the **Yeelight App** (or Xiaomi Home), go to device settings, and ensure **LAN Control (Local Area Network Control)** is turned **ON**. This opens TCP port `55443` required by OpenRGB.
> - **Offline Device Safeguard (v1.1.7):** The add-on includes an automated concurrent pre-flight reachability probe using 4-packet ICMP ping and direct service port tests (Yeelight TCP `55443`, Kasa TCP `9999`, WiZ UDP `38899`). Any light that is temporarily switched off at the wall or has LAN Control disabled is safely excluded from `OpenRGB.json` with a detailed log notice, preventing OpenRGB from freezing on dead sockets (`DetectionManager` 60s timeout) and ensuring USB peripherals always initialize instantly.

---

## Audio-Reactive Sync with LedFx Add-on

To sync real-time audio effects and music visualization with your OpenRGB devices and smart lights, install the **LedFx Add-on** for Home Assistant:

1. **Add LedFx Repository to Home Assistant:**
   - Go to **Settings → Add-ons → Add-on Store**.
   - Click the **⋮ (three dots)** in the top-right corner and select **Repositories**.
   - Add the official LedFx community repository:
     ```text
     https://github.com/adamoberley/ha-addons
     ```
   - Repository source: [adamoberley/ha-addons on GitHub](https://github.com/adamoberley/ha-addons)
2. **Install & Start LedFx:**
   - Find **LedFx** in the Add-on Store, click **Install**, and start the add-on.
3. **Connect LedFx to OpenRGB:**
   - Open the **LedFx Web UI**.
   - Go to **Devices → Add Device** and choose **OpenRGB**.
   - **Host:** `127.0.0.1` (or your HAOS LAN IP if running LedFx on another host).
   - **Port:** `6742` (default OpenRGB SDK port).
   - **OpenRGB Device ID:** Enter the numerical device index printed in this add-on's startup log (e.g. `0`, `1`, `2`).
   - Click **Save**. LedFx will now drive audio-reactive RGB effects through your hardware and smart lights!

---

## Quick Installation

1. In Home Assistant, go to **Settings → Add-ons → Add-on Store**.
2. Click the **⋮ (three dots)** menu in the top-right corner and select **Repositories**.
3. Add this repository URL:
   ```text
   https://github.com/kali-777/ha-openrgb-addon
   ```
4. If already added, click **Check for updates** in the three dots menu, open **OpenRGB SDK Server**, and click **Update** to `v1.1.8`.
5. Ensure **Protection mode** is toggled **OFF** on the add-on Info page.

---

## DDC/CI Monitor Control Features

- **Standardized Naming Pattern**: Automatically names all entities as `<vendor>_<model>_monitor_<feature>`:
  - `select.asus_va34vcpsr_monitor_input_source`
  - `number.asus_va34vcpsr_monitor_speaker_volume`
  - `number.asus_va34vcpsr_monitor_brightness`
  - `number.asus_va34vcpsr_monitor_contrast`
  - `switch.asus_va34vcpsr_monitor_audio_mute`
  - `button.asus_va34vcpsr_monitor_switch_to_hdmi_1`
  - `button.asus_va34vcpsr_monitor_switch_to_usb_c`
  - `button.asus_va34vcpsr_monitor_switch_to_displayport_1`
- **Embedded REST API (`port 6743`)**:
  - `GET /displays`: JSON status of all detected displays
  - `GET /rescan`: Immediate synchronous hardware bus rescan and hotplug discovery
  - `GET /input?to=<HDMI-1|USB-C|DisplayPort-1|work|windows|haos>`: Switch active video input
  - `GET /volume?set=<0-100>`: Set monitor hardware speaker volume
  - `GET /mute?set=<on|off>`: Toggle hardware audio mute
  - `GET /brightness?set=<0-100>`: Set display brightness
  - `GET /contrast?set=<0-100>`: Set display contrast
  - `GET /power?set=<on|standby>`: Set display DPMS power state
  - `GET /setvcp?vcp=0xXX&val=0xYY`: Send raw VCP codes

---

## OpenRGB Features

- **OpenRGB `v1.0+` Engine:** Built on `debian:sid-slim` with latest device definitions (HyperX DuoCast, QuadCast 2 S, Razer Ornata V3, etc.).
- **Philips WiZ IP List** (`wiz_ips`) with configurable white channel strategies.
- **Xiaomi Yeelight IP List** (`yeelight_ips`) with fast direct TCP socket control.
- **TP-Link Kasa IP List** (`kasa_ips`).
- **Auto-List Detected Devices on Startup** (`list_devices_on_start: true`).
- **High-Performance Offline Safeguard:** Multi-packet probes and service port checks skip offline lights so startup never freezes.
