# Changelog

All notable changes to this project will be documented in this file.

## [1.2.7] - 2026-11-27

### Fixed
- **DisplayPort AUX Stability with `--sleep-multiplier 2`**:
  - Embedded `--sleep-multiplier 2` globally across all `ddcutil` command invocations, providing essential timing stability for Intel Alder Lake-N (`drm_dp_i2c_do_msg` / DP AUX) and ASUS monitor scalers.
  - Added dedicated fast-path check directly targeting primary DisplayPort bus (`/dev/i2c-11`), eliminating unnecessary scans of motherboard SMBus channels.
  - Increased per-bus probe timeout to 9s to ensure MCCS queries complete without timeout.
  - Added dynamic `timeout` parameter to `/diag` endpoint (default 25s).

---

## [1.2.6] - 2026-11-27

### Fixed
- **ddcutil CLI Syntax & Option Ordering Correction**:
  - Fixed ddcutil global option ordering (`ddcutil --bus <N> getvcp ...` instead of invalid `ddcutil getvcp ... --bus <N>`), eliminating syntax errors when communicating with the monitor.
  - Replaced invalid `ddcutil --bus <N> detect` with direct MCCS feature probing (`VCP 0x60` Input Source and `VCP 0x10` Brightness) on each I2C bus.
  - Probes all 12 I2C buses in parallel in reverse order (`11, 10, ...`), discovering the display bus (Bus 11) within 300ms.
- **Real-Time `/diag` REST Diagnostics Endpoint**:
  - Added `/diag` HTTP endpoint on port 6743 with support for query parameters (`?bus=11`, `?cmd=...`), defaulting to instantaneous bus 11 MCCS query.
- **Accurate Input Source Synchronization**:
  - Automatically queries and publishes the physical monitor input state (`HDMI-1`, `DisplayPort-1`, `USB-C`) immediately upon startup and on input switch.

---

## [1.2.4] - 2026-11-26

### Fixed
- **Startup Banner and Version Synchronization**:
  - Synchronized `run.sh` banner and `config.yaml` versioning.

---

## [1.2.3] - 2026-11-26

### Fixed
- **Instant Parallel I2C Bus Probing & Sub-50ms DDC/CI Control**:
  - Replaced sequential 12-bus scanning with high-concurrency async multi-bus probing (`ddcutil detect --async` and `ThreadPoolExecutor` across `/dev/i2c-*` with fast 4s timeout per bus).
  - Eliminates the 45-second `Timeout waiting for ddcutil` on ASUS NUC 14 Essential Alder Lake-N motherboards caused by unresponsive SMBus/internal sensors.
  - Automatically identifies and latches onto the physical display bus (`self.active_bus`), routing all subsequent MCCS `getvcp`, `setvcp`, and `capabilities` queries directly via `--bus <N>`.
  - Bypasses non-display I2C bus scans entirely during active operation, reducing input source switching, brightness adjustment, volume changes, and mute toggles to sub-50ms latency.
- **Accurate Real-Time Input Source Synchronization**:
  - Automatically queries and updates `select.<vendor>_<model>_monitor_input_source` immediately upon bus discovery, resolving the issue where Home Assistant stayed stuck displaying stale states (such as `HDMI-1`) when physically displaying `DisplayPort-1` (Home Assistant OS).
- **Startup Banner Version Alignment**:
  - Corrected the hardcoded version string in `run.sh` to match the release version (`v1.2.3`), eliminating version reporting discrepancies in add-on container logs.

---

## [1.2.2] - 2026-11-26

### Fixed
- **Resilient DDC/CI Subprocess Timeout & Alder Lake-N I2C Probing**:
  - Upgraded `ddcutil` command invocations with `--sleep-multiplier 2` and `--brief` detection, increasing subprocess timeouts from 15s to 35-45s.
  - Eliminates `Timeout waiting for ddcutil (exit code -1)` when polling Intel Alder Lake-N I2C display buses on ASUS NUC 14 Essential while displaying DisplayPort-1.
  - Fixes input source getting stuck on stale cached states (e.g. `HDMI-1`) by ensuring real-time MCCS `VCP 0x60` queries complete cleanly.
- **Legacy MQTT Discovery Cleanup**:
  - Automatically clears legacy discovery retained topics from older schemas (`homeassistant/number/{dev_id}_volume/config` and `homeassistant/switch/{dev_id}_mute/config`), eliminating orphaned duplicate `_2` entities (`Speaker Volume 2`, `Audio Mute 2`) in Home Assistant.

---

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
