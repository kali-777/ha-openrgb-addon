# Changelog

All notable changes to this project will be documented in this file.

## [1.2.1] - 2026-11-25

### Added
- **Native MQTT Display Availability (`online` / `offline`)**:
  - All auto-discovered monitor entities (`select`, `number`, `switch`, `button`) now include native `availability_topic: "ha_openrgb/ddc/{dev_id}/availability"`.
  - Automatically publishes `online` when a monitor is detected on the I2C bus and `offline` when disconnected or powered off, ensuring Home Assistant entities accurately reflect real hardware status without ghost states.
  - Automatically discovers a native `connectivity` binary sensor: `binary_sensor.<vendor>_<model>_monitor_status`.
- **On-Demand MQTT Bus Rescan Trigger**:
  - The DDC service now subscribes to `ha_openrgb/ddc/rescan`.
  - Publishing any payload to `ha_openrgb/ddc/rescan` (e.g. from Home Assistant `action: mqtt.publish`) triggers an immediate synchronous hardware bus rescan and refreshes all discovery and state topics on demand without requiring REST polling or add-on restarts.

---

## [1.2.0] - 2026-11-24

### Added
- **Automated Philips WiZ Hardware Model & Firmware Discovery**:
  - The pre-flight probe in `run.sh` now automatically queries the native WiZ UDP API (`getSystemConfig` & `getPilot`) over port `38899`.
  - Automatically parses `moduleName` to detect exact hardware models:
    - `DMORGB` -> `Philips WiZ Light Bar (RGBW)`
    - `DHRGB` -> `Philips WiZ Squire Lamp (RGBWW Dual-Head)`
    - `SHRGB` / `SHRGB1C` / `SHRGB2C` -> `Philips WiZ Color Bulb (RGBW)`
    - `SHTW` / `SHTW1C` -> `Philips WiZ Tunable White Bulb`
    - `POLE` -> `Philips WiZ Pole Floor Light`
    - `STRIP` -> `Philips WiZ Lightstrip (RGB)`
  - Outputs full hardware diagnostics at startup: e.g. `Philips WiZ Light Bar (RGBW) (model: DMORGB, FW: 1.39.2, RSSI: -54 dBm, MAC: 9877d5421304)`.
  - Makes mapping OpenRGB device index (`2: Philips Wiz`) in LedFx instantaneous and foolproof alongside Yeelight and USB peripherals.

---

## [1.1.10] - 2026-11-24

### Fixed
- **Resilient Multi-Attempt WiZ UDP Probing & Wi-Fi Jitter Tolerance**:
  - Upgraded the Philips WiZ pre-flight reachability probe in `run.sh` from a single 1.5s UDP query to 3 sequential UDP attempts with 3.0s timeout, plus a 5-packet ICMP fallback with 4.0s timeout.
  - Prevents false-negative offline skips during Wi-Fi congestion, router re-associations, or power-cut recovery when 2.4GHz latency spikes (up to 3,500ms).
  - Automatically parses WiZ `getPilot` responses to display real-time signal strength (`RSSI: -XX dBm`) and hardware MAC address directly in the add-on startup log.
- **Extended TCP Timeouts for Yeelight & Kasa**:
  - Increased Yeelight and Kasa TCP reachability timeouts to 3.5s and 3.0s respectively, with 5-packet ICMP ping fallback.

---

## [1.1.9] - 2026-11-23

### Added
- **Automated Yeelight Hardware Model & Name Discovery**:
  - The pre-flight probe in `run.sh` now automatically queries the Yeelight Open API (`get_prop ["name", "model"]`) across all responsive devices over TCP `55443`.
  - Automatically identifies and logs the exact hardware model name (e.g. `stripe` -> `Yeelight Light Strip Plus`, `color` -> `Mi LED Smart Bulb Color`, `bslamp1` -> `Mi Bedside Lamp 1`) right above OpenRGB device enumeration, making it effortless to map device indices (`3`, `4`, `5`, `6`) in LedFx.

### Documentation
- Added important operational guidance in `README.md` and `DOCS.md` regarding the need to restart the LedFx add-on (up to 2x) whenever adding or removing smart lights so LedFx flushes its device cache and establishes a clean connection to the OpenRGB SDK server.

---

## [1.1.8] - 2026-11-23

### Fixed
- **Permanent Elimination of Yeelight Reverse-Socket Deadlock**:
  - OpenRGB's experimental `music_mode: true` requires physical bulbs to reverse-connect to an internal TCP listener port. Inside Home Assistant OS Docker, bulbs receive the container's private hostname/IP (`gethostname`) which they cannot reach, causing OpenRGB's detection thread to block in `tcp_server_listen()` for 60,000ms until killed by `DetectionManager`.
  - Enforced `music_mode: false` unconditionally in `run.sh`, overriding any legacy `/data/options.json` values and retiring the broken option from `config.yaml`. OpenRGB now controls Yeelight bulbs exclusively over standard local TCP port `55443` with zero blocking and sub-10ms startup.
- **Accurate Yeelight Port 55443 Diagnostic Logging**:
  - The pre-flight probe now specifically distinguishes between `ConnectionRefusedError` (device is online and pingable, but LAN Control is disabled in the Yeelight app) and socket timeout (device is powered off at wall switch).

---

## [1.1.7] - 2026-11-23

### Fixed
- **Unprotected Mode Prerequisite Documentation for DDC/CI**:
  - Added explicit instructions and documentation in `README.md`, `DOCS.md`, and container logs noting that **"Protection mode" must be toggled OFF** ("Unprotected mode") on the add-on's Info page in Home Assistant.
  - Resolves `EPERM` (Operation not permitted) on `/dev/i2c-*` so `ddcutil` can communicate freely with computer monitors without Docker AppArmor confinement.
- **Robust Multi-Packet Ping & Port 55443 Reachability Probe**:
  - Upgraded reachability probe in `run.sh` from single-packet to 4-packet ping (`ping -c 4 -W 2`) to reliably tolerate jitter and latency spikes on 2.4GHz Wi-Fi networks (e.g. bulbs waking from sleep or experiencing high latency).

---

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
- **Input Source & Hardware Terse Parsing**: Fixed hex parser for `ddcutil getvcp 60 --terse` to handle `x11`, `x0f`, `x1a` values without leading zero, eliminating initial null/unknown input state.\n- **Hardware Speaker Volume & Audio Mute Discovery**: Added regex fallback parser for `ddcutil getvcp 62` (`Audio speaker volume`) and `8D` (`Audio mute`), properly surfacing volume and mute controls for internal monitor speakers.\n- **Real-Time App Logging**: Added `PYTHONUNBUFFERED=1` and `-u` flag to `ddc_service.py` to stream all DDC hardware diagnostics directly into the Home Assistant App Logs in real time.\n- **Masked Password Field**: Configured `mqtt_password: "password"` in add-on schema to securely mask MQTT broker passwords in the Home Assistant UI.\n\n---\n\n## [1.1.3] - 2026-11-23\n\n### Fixed\n- **I2C Device Permissions & AppArmor Bypass**: Disabled default container AppArmor confinement (`apparmor: false`) and granted explicit Linux capabilities `SYS_ADMIN` and `SYS_RAWIO` in `config.yaml`. Resolves `ddcutil` error `EPERM(1): Operation not permitted` on `/dev/i2c-11` (and all motherboard I2C buses), allowing unhindered communication with ASUS VA34VCPSR and other DDC/CI monitors.\n- **Automated Mosquitto MQTT Discovery via Supervisor API**: Enabled `hassio_api: true` and implemented direct token authentication against `http://supervisor/services/mqtt`. Automatically discovers and connects to the Mosquitto broker with zero manual credential entry required, eliminating MQTT code 135 (Not authorized).\n- **Manual Credentials Fallback**: Full support for manual `mqtt_username` and `mqtt_password` in options for external brokers or custom users.\n- **Repository Metadata & Branding Restoration**: Fixed add-on catalog sync to ensure the OpenRGB logo, documentation tab, changelog, and update badges persist without supervisor detachment.\n\n---\n\n## [1.1.2] - 2026-11-23\n\n### Fixed\n- **Repository Schema Validation & Logo Recovery**: Fixed `config.yaml` schema compliance with Home Assistant Supervisor (`SCHEMA_ADDON_CONFIG`) by removing redundant `devices` list under `full_access: true`, resolving `password?` schema type, and eliminating detached add-on status so the official OpenRGB logo, documentation, and update indicators restore properly in the HA UI.\n- **DDC/CI Display Detection**: Robust stdout display parsing in `ddc_service.py` to process connected displays regardless of non-zero scan warning codes on motherboard I2C buses.\n- **MQTT Authentication**: Added support for authenticated connections (`mqtt_username` and `mqtt_password`), eliminating Mosquitto error `code 5`.\n- **paho-mqtt 2.x Upgrade**: Eliminated Callback API v1 deprecation warnings.\n\n---\n\n## [1.1.0] - 2026-11-23\n\n### Added\n- **Generic DDC/CI Hardware Monitor Controller**:\n  - Full hardware control via `/dev/i2c-*` bus using `ddcutil`.\n  - **Dynamic Input Source Switching (`VCP 0x60`)**: Switch seamlessly between `HDMI-1` (Personal Windows), `USB-C` (Work Laptop), and `DisplayPort-1` (Home Assistant OS / Mini PC).\n  - **Hardware Audio Speaker Volume (`VCP 0x62`) & Mute (`VCP 0x8D`)**: Control internal monitor DAC/amplifier volume directly from Home Assistant or physical rotary dials.\n  - **Circadian & Lux Backlight / Contrast Control**: Adjust brightness (`VCP 0x10`) and contrast (`VCP 0x12`) in sync with smart home lighting curves.\n  - **Display Power & DPMS Control (`VCP 0xD6`)**: Standby, suspend, and wake display panels automatically.\n  - **Dynamic Home Assistant MQTT Auto-Discovery**:\n    - Generates clean, standardized entity IDs following `<vendor>_<model>_monitor_<feature>`:\n      - `select.<vendor>_<model>_monitor_input_source` (e.g. `select.asus_va34vcpsr_monitor_input_source`)\n      - `number.<vendor>_<model>_monitor_speaker_volume`\n      - `number.<vendor>_<model>_monitor_brightness`\n      - `number.<vendor>_<model>_monitor_contrast`\n      - `switch.<vendor>_<model>_monitor_audio_mute`\n      - `button.<vendor>_<model>_monitor_switch_to_<input>` (e.g. `button.asus_va34vcpsr_monitor_switch_to_hdmi_1`)\n  - **Embedded High-Performance REST API (`port 6743`)**:\n    - `GET /displays`: Full JSON diagnostics of detected displays, current inputs, volume, and capabilities.\n    - `GET /rescan`: Immediate synchronous hardware bus rescan and hotplug discovery.\n    - `GET /input?to=<source>`: Instant input switching (accepts `HDMI-1`, `USB-C`, `DisplayPort-1`, `work`, `windows`, `haos`, or hex `0x11`).\n    - `GET /volume?set=<0-100>`: Set hardware speaker volume.\n    - `GET /mute?set=<on|off>`: Toggle hardware audio mute.\n    - `GET /brightness?set=<0-100>`: Adjust backlight intensity.\n    - `GET /contrast?set=<0-100>`: Adjust contrast level.\n    - `GET /power?set=<on|standby>`: Control display panel power.\n    - `GET /setvcp?vcp=0xXX&val=0xYY`: Raw low-level VCP register access.\n  - Bundled `ddcutil` and `python3-paho-mqtt` in add-on container.\n\n---\n\n## [1.0.3] - 2026-11-22\n\n### Added\n- Native USB HID support for HyperX DuoCast/QuadCast USB microphones.\n- Razer Ornata V3 keyboard USB integration.\n- Philips WiZ light bar bridging with selectable white channel strategies (`Average`, `Lowest`, `None`).\n- Dedicated TCP OpenRGB SDK server listening on `0.0.0.0:6742`.\n\n---\n\n## [1.0.2] - 2026-11-21\n\n### Added\n- Xiaomi Yeelight TCP Fast Music Mode streaming support.\n- TP-Link Kasa smart Wi-Fi lighting integration.\n\n---\n\n## [1.0.1] - 2026-11-20\n\n### Added\n- Automated startup device enumeration in log (`openrgb --list-devices`).\n- Multi-architecture build support (`amd64`, `aarch64`, `armv7`).\n\n---\n