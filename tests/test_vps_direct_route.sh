#!/usr/bin/env bash
# Unit checks for the VPS Clash-TUN bypass. Does not add routes.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
script="$root/scripts/ensure-vps-direct-route.sh"
installer="$root/scripts/install-vps-direct-route.sh"
tunnel="$root/scripts/run-web-tunnel.sh"

bash -n "$script"
bash -n "$installer"
bash -n "$tunnel"

grep -q '175.24.134.228' "$script"
grep -q 'ipconfig getoption' "$script"
grep -q '198.18.0.1' "$script"

# Must not bake in today's campus/Wi-Fi gateway.
if grep -E '10\.194\.39\.150|192\.168\.1\.1|192\.168\.0\.1' "$script" "$installer"; then
  echo "scripts hardcode a LAN gateway" >&2
  exit 1
fi

python3 - <<'PY'
from pathlib import Path
text = Path("scripts/install-vps-direct-route.sh").read_text()
if "LaunchDaemons" not in text:
    raise SystemExit("installer does not install a LaunchDaemon")
if "ensure-vps-direct-route.sh" not in text:
    raise SystemExit("installer does not install the route helper")
if "10.194.39.150" in text:
    raise SystemExit("installer hardcodes a Wi-Fi gateway")
PY

# Mocked route-get: Clash TUN must be treated as NOT direct.
tun_get="$(mktemp)"
en_get="$(mktemp)"
trap 'rm -f "$tun_get" "$en_get"' EXIT
cat >"$tun_get" <<'EOF'
   route to: 175.24.134.228
destination: 175.24.134.228
    gateway: 198.18.0.1
  interface: utun4
EOF
cat >"$en_get" <<'EOF'
   route to: 175.24.134.228
destination: 175.24.134.228
    gateway: 10.0.0.1
  interface: en0
EOF

if KILN_ROUTE_GET_FILE="$tun_get" bash "$script" --check; then
  echo "TUN route was accepted as direct" >&2
  exit 1
fi
KILN_ROUTE_GET_FILE="$en_get" bash "$script" --check

# Physical default must skip utun even if it appears first.
phys="$(mktemp)"
cat >"$phys" <<'EOF'
    gateway: 198.18.0.1
  interface: utun4
EOF
out="$(KILN_DEFAULT_ROUTE_FILE="$phys" KILN_PHYSICAL_ROUTER_OVERRIDE='en0 10.0.0.1' bash "$script" --print-physical)"
test "$out" = "en0 10.0.0.1"

# Tunnel must refuse to SSH while the VPS is still captured by Clash TUN.
grep -q 'refusing to open a zombie forward' "$tunnel"
grep -q 'ensure-vps-direct-route.sh' "$tunnel" || grep -q 'KILN_VPS_DIRECT_ROUTE' "$tunnel"
