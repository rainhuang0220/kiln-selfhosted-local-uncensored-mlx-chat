#!/usr/bin/env bash
set -euo pipefail

work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT
mkdir -p "$work_dir/model"
touch "$work_dir/model/config.json"

output="$(bash scripts/activate-model.sh --dry-run "$work_dir/model" "demo-model")"
grep -Fqx "model_path=$work_dir/model" <<<"$output"
grep -Fqx 'model_name=demo-model' <<<"$output"
