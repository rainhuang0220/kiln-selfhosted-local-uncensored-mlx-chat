#!/usr/bin/env bash
# Reverse SSH: VPS 127.0.0.1:17777 -> this Mac 127.0.0.1:7777
# Does not replace com.kiln.mlx or com.kiln.mtplx-tunnel.
set -euo pipefail

REMOTE="${KILN_TUNNEL_REMOTE:-ubuntu@175.24.134.228}"
LISTEN="${KILN_TUNNEL_LISTEN:-127.0.0.1:17777}"
LOCAL="${KILN_TUNNEL_LOCAL:-127.0.0.1:7777}"
AGENTS="$HOME/Library/LaunchAgents"
LABEL="com.kiln.web-tunnel"
PLIST="$AGENTS/${LABEL}.plist"
UID_NUM="$(id -u)"
DOMAIN="gui/${UID_NUM}/${LABEL}"

mkdir -p "$AGENTS"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>${LABEL}</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/ssh</string>
    <string>-N</string>
    <string>-T</string>
    <string>-o</string><string>ExitOnForwardFailure=yes</string>
    <string>-o</string><string>ServerAliveInterval=30</string>
    <string>-o</string><string>ServerAliveCountMax=3</string>
    <string>-o</string><string>BatchMode=yes</string>
    <string>-R</string><string>${LISTEN}:${LOCAL}</string>
    <string>${REMOTE}</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>15</integer>
  <key>StandardOutPath</key><string>/tmp/kiln-web-tunnel.log</string>
  <key>StandardErrorPath</key><string>/tmp/kiln-web-tunnel.err</string>
</dict></plist>
EOF

launchctl bootout "$DOMAIN" >/dev/null 2>&1 || true
launchctl bootstrap "gui/${UID_NUM}" "$PLIST"
launchctl enable "$DOMAIN" >/dev/null 2>&1 || true
launchctl kickstart -k "$DOMAIN"
echo "installed $DOMAIN"
echo "forwards ${LISTEN} -> ${LOCAL} via ${REMOTE}"
