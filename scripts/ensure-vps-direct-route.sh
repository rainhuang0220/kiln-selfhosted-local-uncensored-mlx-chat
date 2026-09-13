#!/usr/bin/env bash
# Keep a durable UGHS /32 for the VPS on the physical gateway, not Clash TUN.
# A cloned default via en0 (WASCLONED) is not enough: Clash 128.0/1 wins on the next TUN rebuild.
set -u

VPS_IP="${KILN_VPS_IP:-175.24.134.228}"
LOG="${KILN_ROUTE_WATCH_LOG:-/tmp/kiln-vps-direct-route.log}"
PHYS_TRIES="${KILN_PHYS_TRIES:-8}"
PHYS_SLEEP="${KILN_PHYS_SLEEP:-2}"

route_get() {
  if [[ -n "${KILN_ROUTE_GET_FILE:-}" ]]; then
    cat "$KILN_ROUTE_GET_FILE"
  else
    /sbin/route -n get "$VPS_IP" 2>/dev/null || true
  fi
}

default_get() {
  if [[ -n "${KILN_DEFAULT_ROUTE_FILE:-}" ]]; then
    cat "$KILN_DEFAULT_ROUTE_FILE"
  else
    /sbin/route -n get default 2>/dev/null || true
  fi
}

host_routes() {
  if [[ -n "${KILN_HOST_ROUTE_FILE:-}" ]]; then
    cat "$KILN_HOST_ROUTE_FILE"
  else
    netstat -rn -f inet 2>/dev/null || true
  fi
}

is_tun_iface() {
  [[ "${1:-}" == utun* || "${1:-}" == ipsec* ]]
}

is_clash_gw() {
  [[ "${1:-}" == 198.18.* ]]
}

ts() { date -u +%FT%TZ; }

log_line() {
  echo "$*" | tee -a "$LOG"
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
  return 1
}

wait_physical() {
  local n=1 phys
  while [[ "$n" -le "$PHYS_TRIES" ]]; do
    if phys=$(print_physical); then
      echo "$phys"
      return 0
    fi
    sleep "$PHYS_SLEEP"
    n=$((n + 1))
  done
  return 1
}

has_ughs() {
  host_routes | awk -v ip="$VPS_IP" '$1==ip && $3 ~ /H/ {found=1} END { exit !found }'
}

route_snapshot() {
  local text gw iface flags
  text=$(route_get)
  gw=$(printf '%s\n' "$text" | awk '/gateway:/{print $2; exit}')
  iface=$(printf '%s\n' "$text" | awk '/interface:/{print $2; exit}')
  flags=$(printf '%s\n' "$text" | awk '/flags:/{print; exit}')
  echo "${iface:-none}/${gw:-none}"
  if has_ughs; then
    echo ughs
  elif [[ "${flags:-}" == *WASCLONED* ]]; then
    echo cloned
  elif is_tun_iface "${iface:-}" || is_clash_gw "${gw:-}"; then
    echo tun
  else
    echo other
  fi
}

check_direct() {
  local text gw iface
  text=$(route_get)
  gw=$(printf '%s\n' "$text" | awk '/gateway:/{print $2; exit}')
  iface=$(printf '%s\n' "$text" | awk '/interface:/{print $2; exit}')
  if [[ -z "${iface:-}" || -z "${gw:-}" ]]; then
    return 1
  fi
  if is_tun_iface "$iface" || is_clash_gw "$gw"; then
    return 1
  fi
  has_ughs
}

tcp22() {
  if [[ -n "${KILN_SKIP_TCP22:-}" ]]; then
    echo skip
    return 0
  fi
  python3 - "$VPS_IP" <<'PY'
import socket, sys
ip = sys.argv[1]
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(3)
try:
    s.connect((ip, 22))
except Exception:
    sys.exit(1)
finally:
    s.close()
PY
}

apply() {
  local phys iface gw before_pair before_kind after_pair after_kind action t22 result
  if ! phys=$(wait_physical); then
    log_line "ts=$(ts) physical_iface=none physical_gateway=none route_before=$(route_snapshot | tr '\n' ' ') action=none route_after=unchanged tcp22=skip result=PHYS_UNAVAILABLE"
    return 1
  fi
  iface=${phys%% *}
  gw=${phys##* }
  before_pair=$(route_snapshot | sed -n '1p')
  before_kind=$(route_snapshot | sed -n '2p')
  action=none
  if check_direct; then
    local cur_gw
    cur_gw=$(route_get | awk '/gateway:/{print $2; exit}')
    if [[ "$cur_gw" == "$gw" ]]; then
      action=already
    fi
  fi
  if [[ "$action" != already ]]; then
    /sbin/route -n delete -host "$VPS_IP" >/dev/null 2>&1 || true
    if /sbin/route -n add -host "$VPS_IP" "$gw" >/dev/null 2>&1; then
      action=add
    else
      if /sbin/route -n change -host "$VPS_IP" "$gw" >/dev/null 2>&1; then
        action=change
      else
        action=failed
      fi
    fi
  fi
  after_pair=$(route_snapshot | sed -n '1p')
  after_kind=$(route_snapshot | sed -n '2p')
  t22=skip
  if tcp22 >/dev/null 2>&1; then
    t22=ok
  else
    t22=fail
  fi
  if check_direct; then
    result=ok
  else
    result=ROUTE_NOT_DURABLE
  fi
  log_line "ts=$(ts) physical_iface=$iface physical_gateway=$gw route_before=${before_pair}/${before_kind} action=$action route_after=${after_pair}/${after_kind} tcp22=$t22 result=$result"
  [[ "$result" == ok ]]
}

case "${1:---apply}" in
  --check) check_direct ;;
  --print-physical) print_physical ;;
  --apply) apply ;;
  --watch)
    while true; do
      apply || true
      sleep 10
    done
    ;;
  *)
    echo "usage: $0 --check | --print-physical | --apply | --watch" >&2
    exit 2
    ;;
esac
