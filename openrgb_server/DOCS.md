# OpenRGB SDK Server & DDC/CI Monitor Control Add-on Documentation

## Overview
This Home Assistant OS add-on combines two powerful hardware control engines into a single lightweight daemon:
1. **Headless OpenRGB SDK Server (`v1.0+`)**: Direct USB HID peripheral RGB control (HyperX DuoCast, Razer, etc.) and Wi-Fi smart light bridging (Philips WiZ, Xiaomi Yeelight, TP-Link Kasa) for LedFx and Home Assistant.
2. **Generic DDC/CI Hardware Monitor Controller**: Direct I2C/DDC bus control of connected computer monitors via `ddcutil`, enabling input switching (HDMI, DisplayPort, USB-C), hardware speaker volume, mute, brightness, and power management without needing custom OS display drivers or Docker sidecars.

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
> - **Offline Device Safeguard (v1.1.8):** The add-on includes an automated concurrent pre-flight reachability probe using 4-packet ICMP ping and direct service port tests (Yeelight TCP `55443`, Kasa TCP `9999`, WiZ UDP `38899`). Any light that is temporarily switched off at the wall or has LAN Control disabled is safely excluded from `OpenRGB.json` with a detailed log notice, preventing OpenRGB from freezing on dead sockets (`DetectionManager` 60s timeout) and ensuring USB peripherals always initialize instantly.

---

## Hardware Monitor Control (DDC/CI)

### Key Capabilities
- **Input Source Switching (`VCP 0x60`)**: Switch between work laptops, gaming PCs, and server consoles instantly via Home Assistant dashboard buttons, automations, or physical Stream Dock dials.
- **Hardware Audio Speaker Volume (`VCP 0x62`) & Mute (`VCP 0x8D`)**: Control internal monitor stereo speakers directly from HA sliders or rotary knobs.
- **Circadian & Lux Backlight / Contrast (`VCP 0x10` & `0x12`)**: Dynamically sync monitor brightness with room illuminance or time-of-day curves.
- **Display Power / Standby (`VCP 0xD6`)**: Put monitor panels into low-power standby mode when you leave the office.
- **Dynamic Hotplug Rescan**: Background thread periodically probes for newly attached or powered-on displays and automatically registers them with Home Assistant via MQTT Discovery as soon as they receive AC power.

### Home Assistant MQTT Auto-Discovery Entities
When `ddc_mqtt_discovery: true` (default), the add-on automatically detects all connected DDC-capable monitors and publishes native Home Assistant entities named with the pattern `<vendor>_<model>_monitor_<feature>`:

| Entity Type | Entity ID Example | Description |
| :--- | :--- | :--- |
| `select` | `select.asus_va34vcpsr_monitor_input_source` | Dropdown selector with detected input sources (`HDMI-1`, `USB-C`, `DisplayPort-1`) |
| `number` | `number.asus_va34vcpsr_monitor_speaker_volume` | Volume slider (0 - 100%) for monitor's internal speakers |
| `switch` | `switch.asus_va34vcpsr_monitor_audio_mute` | Toggle switch to mute/unmute monitor audio |
| `number` | `number.asus_va34vcpsr_monitor_brightness` | Backlight brightness slider (0 - 100%) |
| `number` | `number.asus_va34vcpsr_monitor_contrast` | Display contrast slider (0 - 100%) |
| `button` | `button.asus_va34vcpsr_monitor_switch_to_hdmi_1` | One-click button to switch directly to HDMI-1 |
| `button` | `button.asus_va34vcpsr_monitor_switch_to_usb_c` | One-click button to switch directly to USB-C |
| `button` | `button.asus_va34vcpsr_monitor_switch_to_displayport_1` | One-click button to switch directly to DisplayPort-1 |

---

## Embedded REST API Reference (Port 6743)

The add-on runs an embedded HTTP REST server on port `6743` (configurable) for direct local network control:

### Endpoints

- **`GET /displays`** (or `/status`):
  Returns a full JSON list of detected monitors, active input, volume, brightness, and capabilities.

- **`GET /rescan`** (or `/detect`):
  Forces an immediate synchronous hardware bus rescan, detects newly powered-on or hotplugged monitors, and re-publishes Home Assistant MQTT discovery topics.

- **`GET /input?to=<source>&display=1`**:
  Switches the active display input. Accepts input names or hex codes:
  - `to=HDMI-1` or `to=0x11` (Personal Windows Laptop)
  - `to=USB-C` or `to=0x1a` (Work Laptop)
  - `to=DisplayPort-1` or `to=0x0f` (Home Assistant OS / Mini PC)
  - Shortcuts: `to=work`, `to=windows`, `to=haos`

- **`GET /volume?set=<0-100>&display=1`**:
  Sets monitor internal speaker amplifier volume.

- **`GET /mute?set=<on|off>&display=1`**:
  Mutes or unmutes monitor audio.

- **`GET /brightness?set=<0-100>&display=1`**:
  Sets display backlight level.

- **`GET /contrast?set=<0-100>&display=1`**:
  Sets display contrast level.

- **`GET /power?set=<on|standby|off>&display=1`**:
  Controls DPMS display power mode (`on`, `standby`, `suspend`, `off`).

- **`GET /setvcp?vcp=0xXX&val=0xYY&display=1`**:
  Sends a raw VCP feature code and value directly to the monitor.

---

## Home Assistant Automation Examples

### 1. Switch to Work Laptop (USB-C) on Workday Morning
```yaml
alias: "Office: Switch Monitor to Work Laptop"
trigger:
  - trigger: time
    at: "09:00:00"
condition:
  - condition: time
    weekday:
      - mon
      - tue
      - wed
      - thu
      - fri
action:
  - action: select.select_option
    target:
      entity_id: select.asus_va34vcpsr_monitor_input_source
    data:
      option: "USB-C"
  - action: number.set_value
    target:
      entity_id: number.asus_va34vcpsr_monitor_brightness
    data:
      value: 75
```

### 2. Switch to Personal Windows PC (HDMI-1) in the Evening
```yaml
alias: "Office: Switch Monitor to Personal PC"
trigger:
  - trigger: time
    at: "18:00:00"
action:
  - action: select.select_option
    target:
      entity_id: select.asus_va34vcpsr_monitor_input_source
    data:
      option: "HDMI-1"
```

---

## Configuration Options

| Option | Default | Description |
| :--- | :--- | :--- |
| `enable_ddc` | `true` | Enables generic DDC/CI monitor control and REST API. |
| `ddc_port` | `6743` | TCP port for the DDC REST API. |
| `ddc_mqtt_discovery` | `true` | Enables Home Assistant MQTT auto-discovery for all detected monitors. |
| `ddc_poll_interval` | `60` | Polling interval in seconds to sync monitor state changes to HA. |
| `mqtt_username` | `""` | Username for Mosquitto broker (optional; automatically fetched from Supervisor API). |
| `mqtt_password` | `""` | Password for Mosquitto broker (optional; automatically fetched from Supervisor API). |
| `server_port` | `6742` | TCP port for the OpenRGB SDK Server (used by LedFx and HA OpenRGB). |
| `server_host` | `0.0.0.0` | Listen address for OpenRGB SDK server. |
| `list_devices_on_start` | `true` | Prints all detected OpenRGB IDs in the add-on log on startup. |
| `wiz_ips` | `["192.168.2.65"]` | List of Philips WiZ static IP addresses. |
| `wiz_white_strategy` | `"Average"` | White LED calculation mode for WiZ lights (`Average`, `Lowest`, `None`). |
| `yeelight_ips` | `[]` | List of Xiaomi Yeelight static IP addresses. |
| `kasa_ips` | `[]` | List of TP-Link Kasa smart light IP addresses. |
| `extra_args` | `""` | Additional CLI flags passed to `openrgb`. |

---

## OpenRGB & LedFx Audio Reactive Setup

### 1. Install the LedFx Add-on in Home Assistant
LedFx provides real-time music visualization and audio synchronization across RGB hardware and network lights:
1. In Home Assistant, navigate to **Settings → Add-ons → Add-on Store**.
2. Click the three dots (**⋮**) in the top right corner and select **Repositories**.
3. Add the official LedFx repository:
   ```text
   https://github.com/adamoberley/ha-addons
   ```
4. Find **LedFx** in the Add-on Store, click **Install**, and start the add-on.

### 2. Connect LedFx to OpenRGB SDK Server
1. Check this add-on's **Log** tab on startup to see your detected OpenRGB device IDs (e.g., `0: Razer Ornata V3`, `1: HyperX DuoCast`, `2: Philips Wiz`).
2. Open the **LedFx Web UI** → **Devices** → **Add Device**.
3. Select **`openrgb`** from the device type dropdown:
   - **Host:** `127.0.0.1` (or your HAOS IP `192.168.x.x` if running LedFx externally)
   - **Port:** `6742`
   - **OpenRGB ID:** Enter the corresponding numerical device index from the add-on startup log.
4. Click **Save**. LedFx can now send audio-reactive RGB effects directly to your hardware and smart lights!

> [!TIP]
> **Important: Restart LedFx When Adding or Removing Lights:**
> LedFx caches the OpenRGB device list and its client connection. Whenever you add, remove, or change smart light IPs or USB hardware:
> 1. Check this add-on's startup log for your updated device IDs (e.g. `0: Razer...`, `1: HyperX...`, `2: WiZ...`, `3: Yeelight...`).
> 2. **Restart the LedFx add-on** (if newly configured lights don't appear immediately, restart LedFx a second time) so that LedFx flushes its device cache and establishes a fresh connection to OpenRGB on port 6742.

### 3. Native Home Assistant Entities
For native Home Assistant light entities, go to **Settings → Devices & Services → Add Integration → OpenRGB** and enter Host `127.0.0.1`, Port `6742`.
