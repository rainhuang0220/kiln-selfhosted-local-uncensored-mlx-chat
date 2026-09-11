#!/usr/bin/env bash
# Unit checks for the VPS Clash-TUN bypass. Does not add routes.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
script="$root/scripts/ensure-vps-direct-route.sh"
installer="$root/scripts/install-vps-direct-route.sh"
tunnel="$root/scripts/run-web-tunnel.sh"
diag="$root/scripts/check-public-path.sh"

bash -n "$script"
bash -n "$installer"
bash -n "$tunnel"
bash -n "$diag"

grep -q '175.24.134.228' "$script"
grep -q 'ipconfig getoption' "$script"
grep -q '198.18' "$script"
grep -q 'WASCLONED' "$script"
grep -q 'UGHS' "$script"
grep -q 'ROUTE_NOT_READY' "$tunnel"
grep -q 'ROUTE_OK_TCP22_FAIL' "$tunnel"
grep -q 'LOCAL_TARGET_DOWN' "$tunnel"
grep -q 'REMOTE_LISTENER_LOST' "$tunnel"

# Must not bake in today's campus/Wi-Fi gateway.
if grep -E '10\.194\.39\.150|192\.168\.1\.1|192\.168\.0\.1' "$script" "$installer" "$tunnel" "$diag"; then
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

tun_get="$(mktemp)"
cloned_get="$(mktemp)"
en_get="$(mktemp)"
empty_hosts="$(mktemp)"
ughs_hosts="$(mktemp)"
trap 'rm -f "$tun_get" "$cloned_get" "$en_get" "$empty_hosts" "$ughs_hosts"' EXIT

cat >"$tun_get" <<'EOF'
   route to: 175.24.134.228
destination: 175.24.134.228
    gateway: 198.18.0.1
  interface: utun4
      flags: <UP,GATEWAY,HOST,DONE,WASCLONED,IFSCOPE,IFREF>
EOF
cat >"$cloned_get" <<'EOF'
   route to: 175.24.134.228
destination: 175.24.134.228
    gateway: 10.0.0.1
  interface: en0
      flags: <UP,GATEWAY,HOST,DONE,WASCLONED,IFSCOPE,IFREF>
EOF
cat >"$en_get" <<'EOF'
   route to: 175.24.134.228
destination: 175.24.134.228
    gateway: 10.0.0.1
  interface: en0
      flags: <UP,GATEWAY,HOST,DONE,STATIC>
EOF
: >"$empty_hosts"
cat >"$ughs_hosts" <<'EOF'
175.24.134.228     10.0.0.1           UGHS                en0
EOF

if KILN_ROUTE_GET_FILE="$tun_get" KILN_HOST_ROUTE_FILE="$empty_hosts" bash "$script" --check; then
  echo "TUN route was accepted as direct" >&2
  exit 1
fi

# Cloned default via en0 is what last night's daemon called "already direct".
if KILN_ROUTE_GET_FILE="$cloned_get" KILN_HOST_ROUTE_FILE="$empty_hosts" bash "$script" --check; then
  echo "WASCLONED default was accepted as a durable host route" >&2
  exit 1
fi

KILN_ROUTE_GET_FILE="$en_get" KILN_HOST_ROUTE_FILE="$ughs_hosts" bash "$script" --check

# Physical default must skip utun even if it appears first.
phys="$(mktemp)"
trap 'rm -f "$tun_get" "$cloned_get" "$en_get" "$empty_hosts" "$ughs_hosts" "$phys"' EXIT
cat >"$phys" <<'EOF'
    gateway: 198.18.0.1
  interface: utun4
EOF
out="$(KILN_DEFAULT_ROUTE_FILE="$phys" KILN_PHYSICAL_ROUTER_OVERRIDE='en0 10.0.0.1' bash "$script" --print-physical)"
test "$out" = "en0 10.0.0.1"

grep -q 'refusing to open a zombie forward' "$tunnel" || grep -q 'ROUTE_NOT_READY' "$tunnel"
grep -q 'ensure-vps-direct-route.sh' "$tunnel"
grep -q 'check-public-path' "$diag" || grep -q 'public' "$diag"
