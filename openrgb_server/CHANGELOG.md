# Changelog

All notable changes to this project will be documented in this file.

## [1.1.6] - 2026-11-23

### Added
- **Offline Network Device Safeguard & Fast Pre-Flight Reachability Probes**:
  - Implemented high-performance concurrent ICMP/TCP reachability probes in `run.sh` for all configured smart light IPs (`wiz_ips`, `yeelight_ips`, `kasa_ips`).
  - Automatically identifies and safely excludes offline or unreachable devices (such as powered-off wall switches or IPs added for later) before passing configurations into `OpenRGB.json`.
  - **Eliminates Detection Deadlock:** Prevents OpenRGB's `DetectionManager` from hanging for 60 seconds on dead sockets (`Gave up waiting for detection after 60000 ms`), ensuring USB hardware (Razer keyboards, HyperX microphones) and online smart lights are detected instantaneously with 100% reliability every single startup.

---

## [1.1.5] - 2026-11-23

### Added
- **Dynamic Hotplug Rescan & Auto-Discovery on Monitor Power-On**:
  - The background DDC polling thread now automatically detects when 0 displays are active (e.g. when the monitor was powered off during container startup) and actively rescans `ddcutil detect` every polling cycle until displays are found.
  - Also performs an automated topology check every 5 poll intervals (~5 min) to discover hotplugged or newly powered-on monitors.
  - When power is restored to a monitor (such as turning on the EcoFlow / power strip), the service immediately detects the display (e.g., `ASUS VA34VCPSR`), logs the discovery, and instantly auto-publishes all Home Assistant MQTT Discovery entities (`select`, `number`, `switch`, `button`) without requiring an add-on restart.
- **Dedicated REST API Rescan Endpoints**:
  - Added `GET /rescan` and `GET /detect` on port `6743` (`http://<ha-ip>:6743/rescan`) allowing users or Home Assistant automations to trigger an immediate, synchronous hardware bus rescan on demand.

### Fixed
- **Empty Displays Mutex State**: Corrected `detect_monitors()` to update and lock `manager.monitors` cleanly when zero displays are reported by `ddcutil`, preventing stale display state caching.

---

## [1.1.4] - 2026-11-23

### Fixed
- **ASUS VA34VCPSR Capabilities & USB-C (`0x1A`) Mapping**: Added hardware MCCS input code `0x1A` mapped to `USB-C` for ASUS ultrawide displays. Corrected capabilities parser to read exact physical ports (`DisplayPort-1`, `HDMI-1`, `USB-C`), eliminating non-existent phantom ports (`DisplayPort-2`, `HDMI-2`).
- **Input Source & Hardware Terse Parsing**: Fixed hex parser for `ddcutil getvcp 60 --terse` to handle `x11`, `x0f`, `x1a` values without leading zero, eliminating initial null/unknown input state.
- **Hardware Speaker Volume & Audio Mute Discovery**: Added regex fallback parser for `ddcutil getvcp 62` (`Audio speaker volume`) and `8D` (`Audio mute`), properly surfacing volume and mute controls for internal monitor speakers.
- **Real-Time App Logging**: Added `PYTHONUNBUFFERED=1` and `-u` flag to `ddc_service.py` to stream all DDC hardware diagnostics directly into the Home Assistant App Logs in real time.
- **Masked Password Field**: Configured `mqtt_password: "password"` in add-on schema to securely mask MQTT broker passwords in the Home Assistant UI.

---

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
    - `GET /rescan`: Immediate synchronous hardware bus rescan and hotplug discovery.
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
