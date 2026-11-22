# Changelog

All notable changes to this project will be documented in this file.

## [1.1.3] - 2026-11-23

### Fixed
- **I2C Device Permissions & AppArmor Bypass**: Disabled default container AppArmor confinement (`apparmor: false`) and granted explicit Linux capabilities `SYS_ADMIN` and `SYS_RAWIO` in `config.yaml`. Resolves `ddcutil` error `EPERM(1): Operation not permitted` on `/dev/i2c-11` (and all motherboard I2C buses), allowing unhindered communication with ASUS VA34VCPSR and other DDC/CI monitors.
- **Automated Mosquitto MQTT Discovery via Supervisor API**: Enabled `hassio_api: true` and implemented direct token authentication against `http://supervisor/services/mqtt`. Automatically discovers and connects to the Mosquitto broker with zero manual credential entry required, eliminating MQTT code 135 (Not authorized).
- **Manual Credentials Fallback**: Full support for manual `mqtt_username` and `mqtt_password` in options for external brokers or custom users.
- **Repository Metadata & Branding Restoration**: Fixed add-on catalog sync to ensure the OpenRGB logo, documentation tab, changelog, and update badges persist without supervisor detachment.

---

## [1.1.2] - 2026-11-23

### Fixed
- **Repository Schema Validation & Logo Recovery**: Fixed `config.yaml` schema compliance with Home Assistant Supervisor (`SCHEMA_ADDON_CONFIG`) by removing redundant `devices` list under `full_access: true`, resolving `password?` schema type, and eliminating detached add-on status so the official OpenRGB logo, documentation, and update indicators restore properly in the HA UI.
- **DDC/CI Display Detection**: Robust stdout display parsing in `ddc_service.py` to process connected displays regardless of non-zero scan warning codes on motherboard I2C buses.
- **MQTT Authentication**: Added support for authenticated connections (`mqtt_username` and `mqtt_password`), eliminating Mosquitto error `code 5`.
- **paho-mqtt 2.x Upgrade**: Eliminated Callback API v1 deprecation warnings.

---

## [1.1.0] - 2026-11-23

### Added
- **Generic DDC/CI Hardware Monitor Controller**:
  - Full hardware control via `/dev/i2c-*` bus using `ddcutil`.
  - **Dynamic Input Source Switching (`VCP 0x60`)**: Switch seamlessly between `HDMI-1` (Personal Windows), `USB-C` (Work Laptop), and `DisplayPort-1` (Home Assistant OS / Mini PC).
  - **Hardware Audio Speaker Volume (`VCP 0x62`) & Mute (`VCP 0x8D`)**: Control internal monitor DAC/amplifier volume directly from Home Assistant or physical rotary dials.
  - **Circadian & Lux Backlight / Contrast Control**: Adjust brightness (`VCP 0x10`) and contrast (`VCP 0x12`) in sync with smart home lighting curves.
  - **Display Power & DPMS Control (`VCP 0xD6`)**: Standby, suspend, and wake display panels automatically.
  - **Dynamic Home Assistant MQTT Auto-Discovery**:
    - Generates clean, standardized entity IDs following `<vendor>_<model>_monitor_<feature>`:
      - `select.<vendor>_<model>_monitor_input_source` (e.g. `select.asus_va34vcpsr_monitor_input_source`)
      - `number.<vendor>_<model>_monitor_speaker_volume`
      - `number.<vendor>_<model>_monitor_brightness`
      - `number.<vendor>_<model>_monitor_contrast`
      - `switch.<vendor>_<model>_monitor_audio_mute`
      - `button.<vendor>_<model>_monitor_switch_to_<input>` (e.g. `button.asus_va34vcpsr_monitor_switch_to_hdmi_1`)
  - **Embedded High-Performance REST API (`port 6743`)**:
    - `GET /displays`: Full JSON diagnostics of detected displays, current inputs, volume, and capabilities.
    - `GET /input?to=<source>`: Instant input switching (accepts `HDMI-1`, `USB-C`, `DisplayPort-1`, `work`, `windows`, `haos`, or hex `0x11`).
    - `GET /volume?set=<0-100>`: Set hardware speaker volume.
    - `GET /mute?set=<on|off>`: Toggle hardware audio mute.
    - `GET /brightness?set=<0-100>`: Adjust backlight intensity.
    - `GET /contrast?set=<0-100>`: Adjust contrast level.
    - `GET /power?set=<on|standby>`: Control display panel power.
    - `GET /setvcp?vcp=0xXX&val=0xYY`: Raw low-level VCP register access.
  - Bundled `ddcutil` and `python3-paho-mqtt` in add-on container.

---

## [1.0.3] - 2026-11-22

### Added
- Native USB HID support for HyperX DuoCast/QuadCast USB microphones.
- Razer Ornata V3 keyboard USB integration.
- Philips WiZ light bar bridging with selectable white channel strategies (`Average`, `Lowest`, `None`).
- Dedicated TCP OpenRGB SDK server listening on `0.0.0.0:6742`.

---

## [1.0.2] - 2026-11-21

### Added
- Xiaomi Yeelight TCP Fast Music Mode streaming support.
- TP-Link Kasa smart Wi-Fi lighting integration.

---

## [1.0.1] - 2026-11-20

### Added
- Automated startup device enumeration in log (`openrgb --list-devices`).
- Multi-architecture build support (`amd64`, `aarch64`, `armv7`).

---
