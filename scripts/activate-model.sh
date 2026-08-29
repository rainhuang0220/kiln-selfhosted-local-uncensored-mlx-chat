#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
dry_run=false
if [[ "${1:-}" == "--dry-run" ]]; then
  dry_run=true
  shift
fi
MODEL_PATH_INPUT="${1:?usage: activate-model.sh [--dry-run] /absolute/model/path model-id}"
MODEL_NAME_INPUT="${2:?usage: activate-model.sh [--dry-run] /absolute/model/path model-id}"

if [[ ! -d "$MODEL_PATH_INPUT" || ! -f "$MODEL_PATH_INPUT/config.json" ]]; then
  echo "model directory must contain config.json" >&2
  exit 1
fi
if [[ "$MODEL_PATH_INPUT" != /* ]]; then
  echo "model directory must be absolute" >&2
  exit 1
fi

if $dry_run; then
  printf 'model_path=%s\nmodel_name=%s\n' "$MODEL_PATH_INPUT" "$MODEL_NAME_INPUT"
  exit 0
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "automatic model activation requires macOS LaunchAgents" >&2
  exit 1
fi

state_dir="$ROOT/data"
state_file="$state_dir/active-model.env"
mkdir -p "$state_dir"
temp_file="$(mktemp "$state_file.XXXXXX")"
printf 'MODEL_PATH=%q\nMODEL_NAME=%q\n' "$MODEL_PATH_INPUT" "$MODEL_NAME_INPUT" > "$temp_file"
chmod 600 "$temp_file"
mv "$temp_file" "$state_file"

uid_num="$(id -u)"
agent="gui/${uid_num}/com.kiln.mlx"
if ! launchctl print "$agent" >/dev/null 2>&1; then
  "$ROOT/scripts/install-mlx-launchd.sh" >/dev/null
fi
launchctl kickstart -k "$agent"
printf 'activated=%s\n' "$MODEL_NAME_INPUT"
