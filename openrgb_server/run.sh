#!/usr/bin/env bash
set -e

OPTIONS_FILE="/data/options.json"
CONFIG_DIR="/config/OpenRGB"
CONFIG_FILE="${CONFIG_DIR}/OpenRGB.json"

mkdir -p "${CONFIG_DIR}" /etc/udev/rules.d

# Keep ONLY /etc/udev/rules.d/60-openrgb.rules so OpenRGB sees neither missing nor duplicate udev rules
touch /etc/udev/rules.d/60-openrgb.rules
rm -f /usr/lib/udev/rules.d/60-openrgb.rules

# Read options from Home Assistant /data/options.json
SERVER_PORT=$(jq -r '.server_port // 6742' "${OPTIONS_FILE}")
SERVER_HOST=$(jq -r '.server_host // "0.0.0.0"' "${OPTIONS_FILE}")
LOG_LEVEL=$(jq -r '.log_level // "info"' "${OPTIONS_FILE}")
LIST_DEVICES=$(jq -r '.list_devices_on_start // true' "${OPTIONS_FILE}")
WIZ_WHITE_STRATEGY=$(jq -r '.wiz_white_strategy // "Average"' "${OPTIONS_FILE}")
YEELIGHT_MUSIC_MODE=$(jq -r '.yeelight_music_mode // true' "${OPTIONS_FILE}")
EXTRA_ARGS=$(jq -r '.extra_args // ""' "${OPTIONS_FILE}")

echo "=================================================================="
echo " Starting OpenRGB SDK Server Add-on for Home Assistant OS (v1.0.3)"
echo "=================================================================="
echo "OpenRGB Version : $(openrgb --version 2>/dev/null | head -n 1 || echo 'OpenRGB 1.0+')"
echo "Bind Address    : ${SERVER_HOST}:${SERVER_PORT}"
echo "Config Directory: ${CONFIG_DIR}"

# Initialize OpenRGB.json if it does not exist yet
if [ ! -f "${CONFIG_FILE}" ]; then
    echo "{}" > "${CONFIG_FILE}"
fi

# Build PhilipsWizDevices JSON array from wiz_ips option
WIZ_JSON=$(jq -c --arg strategy "${WIZ_WHITE_STRATEGY}" '
  [.wiz_ips[]? | select(length > 0) | {
    ip: .,
    selected_white_strategy: $strategy,
    use_cool_white: false,
    use_warm_white: false
  }]
' "${OPTIONS_FILE}")

# Build YeelightDevices JSON array from yeelight_ips option
YEELIGHT_JSON=$(jq -c --argjson music "${YEELIGHT_MUSIC_MODE}" '
  [.yeelight_ips[]? | select(length > 0) | {
    ip: .,
    music_mode: $music
  }]
' "${OPTIONS_FILE}")

# Build KasaSmartDevices JSON array from kasa_ips option
KASA_JSON=$(jq -c '
  [.kasa_ips[]? | select(length > 0) | {
    ip: .
  }]
' "${OPTIONS_FILE}")

# Merge configured network devices into OpenRGB.json while preserving existing settings/detectors
# Explicitly enable HyperX DuoCast and HyperX QuadCast detectors
TMP_JSON=$(mktemp)
jq \
  --argjson wiz "${WIZ_JSON}" \
  --argjson yee "${YEELIGHT_JSON}" \
  --argjson kasa "${KASA_JSON}" \
  '
  (if ($wiz | length) > 0 then .PhilipsWizDevices = {"devices": $wiz} else .PhilipsWizDevices = null end) |
  (if ($yee | length) > 0 then .YeelightDevices = {"devices": $yee} else .YeelightDevices = null end) |
  (if ($kasa | length) > 0 then .KasaSmartDevices = {"devices": $kasa} else .KasaSmartDevices = null end) |
  .Detectors.detectors["HyperX DuoCast"] = true |
  .Detectors.detectors["HyperX Quadcast S"] = true |
  .Detectors.detectors["HyperX QuadCast 2 S"] = true
  ' "${CONFIG_FILE}" > "${TMP_JSON}" && mv "${TMP_JSON}" "${CONFIG_FILE}"

echo "Configured Philips WiZ IPs : $(echo "${WIZ_JSON}" | jq -r 'map(.ip) | join(", ")')"
echo "Configured Yeelight IPs    : $(echo "${YEELIGHT_JSON}" | jq -r 'map(.ip) | join(", ")')"
echo "Configured Kasa Smart IPs  : $(echo "${KASA_JSON}" | jq -r 'map(.ip) | join(", ")')"

echo "------------------------------------------------------------------"
if [ "${LIST_DEVICES}" = "true" ]; then
    echo "Detected OpenRGB Devices (use these IDs in LedFx):"
    QT_QPA_PLATFORM=offscreen openrgb --config "${CONFIG_DIR}" --noautoconnect --list-devices 2>&1 \
      | grep --line-buffered -vE '(\[Dialog \]|recv_select failed receiving magic)' || true
    echo "------------------------------------------------------------------"
fi

echo "Launching OpenRGB SDK Server on ${SERVER_HOST}:${SERVER_PORT}..."

if [ "${LOG_LEVEL}" = "debug" ] || [ "${LOG_LEVEL}" = "trace" ]; then
    exec openrgb \
        --config "${CONFIG_DIR}" \
        --noautoconnect \
        --server \
        --server-host "${SERVER_HOST}" \
        --server-port "${SERVER_PORT}" \
        --loglevel 6 \
        ${EXTRA_ARGS}
else
    exec openrgb \
        --config "${CONFIG_DIR}" \
        --noautoconnect \
        --server \
        --server-host "${SERVER_HOST}" \
        --server-port "${SERVER_PORT}" \
        ${EXTRA_ARGS} > >(grep --line-buffered -vE '(\[Dialog \]|recv_select failed receiving magic)') 2>&1
fi
