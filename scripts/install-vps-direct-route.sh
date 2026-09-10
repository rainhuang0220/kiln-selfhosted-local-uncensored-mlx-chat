#!/usr/bin/env bash
# Root LaunchDaemon: re-apply the VPS host route after Wi-Fi / DHCP / wake.
# Does not hardcode a LAN gateway. Clash subscription is not touched.
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "run as root (osascript / sudo)" >&2
  exit 1
fi

TARGET_USER="${SUDO_USER:-${KILN_INSTALL_USER:-}}"
if [[ -z "$TARGET_USER" ]]; then
  TARGET_USER=$(stat -f %Su /dev/console)
fi
TARGET_HOME=$(dscl . -read "/Users/${TARGET_USER}" NFSHomeDirectory | awk '{print $2}')
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "${SELF_DIR}/ensure-vps-direct-route.sh" ]]; then
  SRC_HELPER="${SELF_DIR}/ensure-vps-direct-route.sh"
else
  SRC_HELPER="$(cd "${SELF_DIR}/.." && pwd)/scripts/ensure-vps-direct-route.sh"
fi
SUPPORT="${TARGET_HOME}/Library/Application Support/kiln"
LABEL="com.kiln.vps-direct-route"
PLIST="/Library/LaunchDaemons/${LABEL}.plist"
HELPER="${SUPPORT}/ensure-vps-direct-route.sh"

mkdir -p "$SUPPORT"
if [[ "$SRC_HELPER" != "$HELPER" ]]; then
  cp "$SRC_HELPER" "$HELPER"
fi
chmod 755 "$HELPER"
chown "$TARGET_USER:staff" "$HELPER"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>${LABEL}</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string>
    <string>${HELPER}</string>
    <string>--apply</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>StartInterval</key><integer>20</integer>
  <key>WatchPaths</key><array>
    <string>/Library/Preferences/SystemConfiguration</string>
  </array>
  <key>StandardOutPath</key><string>/tmp/kiln-vps-direct-route.log</string>
  <key>StandardErrorPath</key><string>/tmp/kiln-vps-direct-route.err</string>
</dict></plist>
EOF
chmod 644 "$PLIST"

launchctl bootout "system/${LABEL}" >/dev/null 2>&1 || true
launchctl bootstrap system "$PLIST"
launchctl enable "system/${LABEL}" >/dev/null 2>&1 || true
launchctl kickstart -k "system/${LABEL}"
echo "installed system/${LABEL}"
echo "helper ${HELPER}"
bash "$HELPER" --apply || true
bash "$HELPER" --print-physical
/sbin/route -n get 175.24.134.228 || true
