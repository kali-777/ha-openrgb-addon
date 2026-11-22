# Home Assistant Add-on: OpenRGB SDK Server & DDC/CI Monitor Control (`v1.1.0`)

[![Open your Home Assistant instance and show the add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fkali-777%2Fha-openrgb-addon)

Run a headless **OpenRGB SDK Server (`v1.0+`)** and **Generic DDC/CI Hardware Monitor Controller** directly on **Home Assistant OS (HAOS)** (`amd64` / `aarch64` / `armv7`).

Designed to provide two essential capabilities in a single unified daemon:
1. **Generic DDC/CI Monitor Control via `/dev/i2c-*`**: Hardware input source switching (`HDMI-1`, `USB-C`, `DisplayPort-1`), hardware speaker volume (`VCP 0x62`), mute (`VCP 0x8D`), brightness (`VCP 0x10`), and contrast (`VCP 0x12`) with automatic Home Assistant MQTT Discovery (`select`, `number`, `switch`, `button` entities named `<vendor>_<model>_monitor_*`) and an embedded REST API (`port 6743`).
2. **RGB Hardware & Smart Light Bridging for LedFx**: Bridge direct USB RGB peripherals (HyperX DuoCast/QuadCast microphones, Razer keyboards) and Wi-Fi smart lights (Philips WiZ, Xiaomi Yeelight, TP-Link Kasa) to LedFx and Home Assistant 24/7 without needing your desktop PC turned on.

---

## Quick Installation

1. In Home Assistant, go to **Settings → Add-ons → Add-on Store**.
2. Click the **⋮ (three dots)** menu in the top-right corner and select **Repositories**.
3. Add this repository URL:
   ```text
   https://github.com/kali-777/ha-openrgb-addon
   ```
4. If already added, click **Check for updates** in the three dots menu, open **OpenRGB SDK Server**, and click **Update** to `v1.1.0`.

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
- **Xiaomi Yeelight IP List** (`yeelight_ips`) with fast TCP Music Mode streaming.
- **TP-Link Kasa IP List** (`kasa_ips`).
- **Auto-List Detected Devices on Startup** (`list_devices_on_start: true`).
