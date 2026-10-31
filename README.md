# Home Assistant Add-on: OpenRGB SDK Server (`v1.0+`)

[![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fkali-777%2Fha-openrgb-addon)

Run a **headless OpenRGB SDK Server (`v1.0+`)** directly on **Home Assistant OS (HAOS)** (`amd64` / `aarch64` / `armv7`).

Designed to bridge:
- **USB RGB Hardware plugged directly into your HAOS host** (such as **HyperX DuoCast / QuadCast S USB Microphones**, Razer Chroma peripherals, Corsair/ASUS/CoolerMaster controllers)
- **Wi-Fi Smart Lights without native WLED/DDP support** (such as **Philips WiZ Light Bars / Bulbs**, **Xiaomi Yeelight Light Strips / Lamps**, and **TP-Link Kasa**)
- **Real-time Audio Visualizers like the [LedFx HA Add-on](https://github.com/adamoberley/ha-addons)** and **Home Assistant's native [OpenRGB Integration](https://www.home-assistant.io/integrations/openrgb/)** — completely standalone 24/7, even when your desktop PC or ARM64 laptop is powered off!

---

## Quick Installation

1. In Home Assistant, go to **Settings → Add-ons → Add-on Store**.
2. Click the **⋮ (three dots)** menu in the top-right corner and select **Repositories**.
3. Paste this repository URL and click **Add**:
   ```text
   https://github.com/kali-777/ha-openrgb-addon
   ```
4. Refresh the Add-on Store page, scroll to **Kali Home Assistant OS Add-ons (OpenRGB Server)**, click **OpenRGB SDK Server**, and click **Install**.

---

## Features

- **OpenRGB `v1.0+` Engine:** Built on `debian:sid-slim` so newer USB HID devices added after `v0.9` (including **HyperX DuoCast**, **HyperX QuadCast 2 S**, and modern controllers) are detected out-of-the-box.
- **Full HA Configuration UI:**
  - **Custom SDK Server Port** (default `6742`, configurable in UI + network host mode)
  - **Philips WiZ IP List** (`wiz_ips`) — automatically injects `PhilipsWizDevices` into `OpenRGB.json` on startup
  - **Xiaomi Yeelight IP List** (`yeelight_ips`) + `yeelight_music_mode` toggle — automatically injects `YeelightDevices` with fast TCP Music Mode streaming
  - **TP-Link Kasa IP List** (`kasa_ips`) — automatically injects `KasaSmartDevices`
  - **Auto-List Detected Devices on Startup** (`list_devices_on_start: true`) — prints the exact `OPENRGB ID` (`0, 1, 2...`) and LED count of every USB and Wi-Fi device right in the Add-on Log tab so you can copy-paste the ID straight into **LedFx**!
  - **Persistent Config Storage:** Stores `OpenRGB.json` and profiles in `/config/OpenRGB` so custom edits or profiles survive add-on updates and reboots.
