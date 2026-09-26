#!/usr/bin/env bash
# Independent public health probe for Kiln (six states). No generation.
set -euo pipefail
ORIGIN="${1:-https://kiln.plainlist.space}"
LOCAL_API="${KILN_LOCAL_API:-http://127.0.0.1:8787}"
python3 - "$ORIGIN" "$LOCAL_API" <<'PY'
import json, sys, time, urllib.request, urllib.error

origin, local = sys.argv[1], sys.argv[2]

def get(url, timeout=15):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode()
    except Exception as e:
        return 0, str(e)

hs, hb = get(origin + "/")
rs, rb = get(origin + "/readyz")
as_, ab = get(origin + "/auth/status")
ls, lb = get(local + "/health")
readyz, auth, health = {}, {}, {}
try: readyz = json.loads(rb)
except Exception: pass
try: auth = json.loads(ab)
except Exception: pass
try: health = json.loads(lb)
except Exception: pass
out = {
    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "origin": origin,
    "STATIC_UP": hs == 200,
    "PUBLIC_API_UP": rs == 200 or as_ == 200,
    "AUTHENTICATION_UP": as_ == 200 and "ready" in auth,
    "BACKEND_UP": ls == 200,
    "MODEL_AVAILABLE": bool(readyz.get("MODEL_AVAILABLE") or (health.get("provider") or {}).get("http_alive")),
    "END_TO_END_CHAT_UP": "requires_auth",
    "codes": {"homepage": hs, "readyz": rs, "auth_status": as_, "local_health": ls},
    "note": "Unauthenticated probe does not generate.",
}
print(json.dumps(out, indent=2))
PY
