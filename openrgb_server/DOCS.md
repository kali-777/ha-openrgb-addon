# OpenRGB SDK Server & DDC/CI Monitor Control Add-on Documentation

## Overview
This Home Assistant OS add-on combines two powerful hardware control engines into a single lightweight daemon:
1. **Headless OpenRGB SDK Server (`v1.0+`)**: Direct USB HID peripheral RGB control (HyperX DuoCast, Razer, etc.) and Wi-Fi smart light bridging (Philips WiZ, Xiaomi Yeelight, TP-Link Kasa) for LedFx and Home Assistant.
2. **Generic DDC/CI Hardware Monitor Controller**: Direct I2C/DDC bus control of connected computer monitors via `ddcutil`, enabling input switching (HDMI, DisplayPort, USB-C), hardware speaker volume, mute, brightness, and power management without needing custom OS display drivers or Docker sidecars.

---\n## Hardware Monitor Control (DDC/CI)

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

---\n## Embedded REST API Reference (Port 6743)

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

---\n## Home Assistant Automation Examples

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

---\n## Configuration Options

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
| `yeelight_music_mode` | `true` | Enables low-latency TCP Music Mode for Yeelight strips/lamps. |
| `kasa_ips` | `[]` | List of TP-Link Kasa smart light IP addresses. |
| `extra_args` | `""` | Additional CLI flags passed to `openrgb`. |

---\n## OpenRGB & LedFx Setup

1. Start this add-on and check the **Log** tab to see your OpenRGB device indices (e.g., `0: HyperX DuoCast`, `1: Philips WiZ`).
2. Open **LedFx** $\rightarrow$ **Add Device** $\rightarrow$ select **`openrgb`**:
   - Host: `127.0.0.1` (or HAOS LAN IP)
   - Port: `6742`
   - OpenRGB ID: matching device index from log.
3. For Home Assistant native entities, go to **Settings $\rightarrow$ Devices & Services $\rightarrow$ Add Integration $\rightarrow$ OpenRGB** and enter Host `127.0.0.1`, Port `6742`.
