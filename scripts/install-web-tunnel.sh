#!/usr/bin/env bash
# Reverse SSH: VPS 127.0.0.1:17777 -> this Mac 127.0.0.1:7777
# Wrapper lives under Application Support so launchd does not execute Desktop scripts.
# Does not replace com.kiln.mlx or com.kiln.mtplx-tunnel.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SUPPORT="$HOME/Library/Application Support/kiln"
REMOTE="${KILN_TUNNEL_REMOTE:-ubuntu@175.24.134.228}"
LISTEN="${KILN_TUNNEL_LISTEN:-127.0.0.1:17777}"
# Production default: API-only. Vite stays on 127.0.0.1:7777 for local development.
LOCAL="${KILN_TUNNEL_LOCAL:-127.0.0.1:8787}"
AGENTS="$HOME/Library/LaunchAgents"
LABEL="com.kiln.web-tunnel"
PLIST="$AGENTS/${LABEL}.plist"
UID_NUM="$(id -u)"
DOMAIN="gui/${UID_NUM}/${LABEL}"

mkdir -p "$SUPPORT" "$AGENTS"
cp "$ROOT/scripts/run-web-tunnel.sh" "$SUPPORT/run-web-tunnel.sh"
chmod 755 "$SUPPORT/run-web-tunnel.sh"
if [[ -f "$ROOT/scripts/ensure-vps-direct-route.sh" ]]; then
  cp "$ROOT/scripts/ensure-vps-direct-route.sh" "$SUPPORT/ensure-vps-direct-route.sh"
  chmod 755 "$SUPPORT/ensure-vps-direct-route.sh"
fi

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>${LABEL}</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string>
    <string>${SUPPORT}/run-web-tunnel.sh</string>
  </array>
  <key>EnvironmentVariables</key><dict>
    <key>HOME</key><string>${HOME}</string>
    <key>KILN_TUNNEL_REMOTE</key><string>${REMOTE}</string>
    <key>KILN_TUNNEL_LISTEN</key><string>${LISTEN}</string>
    <key>KILN_TUNNEL_LOCAL</key><string>${LOCAL}</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>15</integer>
  <key>StandardOutPath</key><string>/tmp/kiln-web-tunnel.log</string>
  <key>StandardErrorPath</key><string>/tmp/kiln-web-tunnel.err</string>
</dict></plist>
EOF

launchctl bootout "$DOMAIN" >/dev/null 2>&1 || true
if ! launchctl bootstrap "gui/${UID_NUM}" "$PLIST" 2>/dev/null; then
  # Already loaded or bootstrap raced; keep the existing job and reload in place.
  launchctl enable "$DOMAIN" >/dev/null 2>&1 || true
fi
launchctl enable "$DOMAIN" >/dev/null 2>&1 || true
if ! launchctl kickstart -k "$DOMAIN" 2>/dev/null; then
  launchctl bootstrap "gui/${UID_NUM}" "$PLIST"
  launchctl kickstart -k "$DOMAIN"
fi
echo "installed $DOMAIN"
echo "forwards ${LISTEN} -> ${LOCAL} via ${REMOTE}"
echo "logs: /tmp/kiln-web-tunnel.log /tmp/kiln-web-tunnel.err"
