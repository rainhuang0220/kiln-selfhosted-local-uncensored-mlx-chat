#!/usr/bin/env bash
# Read-only snapshot of the Kiln public path. Does not restart anything.
set -u

VPS_IP="${KILN_VPS_IP:-175.24.134.228}"
HOST="${KILN_PUBLIC_HOST:-kiln.plainlist.space}"
REMOTE="${KILN_TUNNEL_REMOTE:-ubuntu@${VPS_IP}}"

echo "ts=$(date -u +%FT%TZ)"
echo "clash=$(pgrep -x 'ClashX Pro' >/dev/null && echo on || echo off)"

rt=$(/sbin/route -n get "$VPS_IP" 2>/dev/null || true)
echo "route_iface=$(printf '%s\n' "$rt" | awk '/interface:/{print $2; exit}')"
echo "route_gw=$(printf '%s\n' "$rt" | awk '/gateway:/{print $2; exit}')"
echo "route_flags=$(printf '%s\n' "$rt" | awk '/flags:/{print; exit}')"
if netstat -rn -f inet | awk -v ip="$VPS_IP" '$1==ip && $3 ~ /H/ {found=1} END{exit !found}'; then
  echo "host_ughs=yes"
else
  echo "host_ughs=no"
fi

if python3 -c "import socket; s=socket.create_connection(('${VPS_IP}', 22), 3); s.close()" 2>/dev/null; then
  echo "tcp22=ok"
else
  echo "tcp22=fail"
fi

if python3 -c "import socket; s=socket.create_connection(('127.0.0.1', 7777), 2); s.close()" 2>/dev/null; then
  echo "local7777=ok"
else
  echo "local7777=fail"
fi

if curl -fsS --max-time 5 http://127.0.0.1:8787/health >/dev/null 2>&1; then
  echo "local8787=ok"
else
  echo "local8787=fail"
fi

pub=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "https://${HOST}/" || echo fail)
echo "public_via_local_resolver=${pub}"

direct=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 --resolve "${HOST}:443:${VPS_IP}" "https://${HOST}/" || echo fail)
echo "public_via_vps_ip=${direct}"

vps17777=$(ssh -o BatchMode=yes -o ConnectTimeout=8 "$REMOTE" 'ss -lntp | grep -q 17777 && curl -fsS -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:17777/' 2>/dev/null || echo fail)
echo "vps17777=${vps17777}"
