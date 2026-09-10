#!/usr/bin/env bash
# Keep 175.24.134.228 on the physical default, not Clash TUN (utun / 198.18.0.1).
# Gateway and interface are discovered each run. Do not hardcode a Wi-Fi router.
set -euo pipefail

VPS_IP="${KILN_VPS_IP:-175.24.134.228}"

route_get() {
  if [[ -n "${KILN_ROUTE_GET_FILE:-}" ]]; then
    cat "$KILN_ROUTE_GET_FILE"
  else
    /sbin/route -n get "$VPS_IP"
  fi
}

default_get() {
  if [[ -n "${KILN_DEFAULT_ROUTE_FILE:-}" ]]; then
    cat "$KILN_DEFAULT_ROUTE_FILE"
  else
    /sbin/route -n get default
  fi
}

is_tun_iface() {
  [[ "$1" == utun* || "$1" == ipsec* ]]
}

is_clash_gw() {
  [[ "$1" == 198.18.* ]]
}

print_physical() {
  if [[ -n "${KILN_PHYSICAL_ROUTER_OVERRIDE:-}" ]]; then
    echo "$KILN_PHYSICAL_ROUTER_OVERRIDE"
    return 0
  fi
  local gw iface i r
  gw=$(default_get | awk '/gateway:/{print $2; exit}')
  iface=$(default_get | awk '/interface:/{print $2; exit}')
  if [[ -n "${iface:-}" && -n "${gw:-}" ]] && ! is_tun_iface "$iface" && ! is_clash_gw "$gw"; then
    echo "$iface $gw"
    return 0
  fi
  for i in en0 en1 en2 en3 bridge0; do
    r=$(ipconfig getoption "$i" router 2>/dev/null || true)
    if [[ -n "${r:-}" ]] && ! is_clash_gw "$r"; then
      echo "$i $r"
      return 0
    fi
  done
  echo "no physical IPv4 default (en0/en1 router)" >&2
  return 1
}

check_direct() {
  local gw iface
  gw=$(route_get | awk '/gateway:/{print $2; exit}')
  iface=$(route_get | awk '/interface:/{print $2; exit}')
  if [[ -z "${iface:-}" || -z "${gw:-}" ]]; then
    return 1
  fi
  if is_tun_iface "$iface" || is_clash_gw "$gw"; then
    return 1
  fi
  return 0
}

apply() {
  local phys iface gw
  phys=$(print_physical)
  iface=${phys%% *}
  gw=${phys##* }
  if [[ -z "$iface" || -z "$gw" || "$iface" == "$gw" ]]; then
    echo "invalid physical default: $phys" >&2
    return 1
  fi
  if check_direct; then
    local cur_gw
    cur_gw=$(route_get | awk '/gateway:/{print $2; exit}')
    if [[ "$cur_gw" == "$gw" ]]; then
      echo "already direct ${VPS_IP} via ${iface} ${gw}"
      return 0
    fi
  fi
  if /sbin/route -n change -host "$VPS_IP" "$gw" 2>/dev/null; then
    echo "changed ${VPS_IP} -> ${gw} (${iface})"
  else
    /sbin/route -n add -host "$VPS_IP" "$gw"
    echo "added ${VPS_IP} -> ${gw} (${iface})"
  fi
  check_direct
}

case "${1:---apply}" in
  --check) check_direct ;;
  --print-physical) print_physical ;;
  --apply) apply ;;
  *)
    echo "usage: $0 --check | --print-physical | --apply" >&2
    exit 2
    ;;
esac
