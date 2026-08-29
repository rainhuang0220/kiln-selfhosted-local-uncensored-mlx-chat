#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -x .venv/bin/uvicorn ]]; then
  echo "Missing venv. From kiln/backend run: uv venv ../.venv && uv pip install --python ../.venv/bin/python -e '.[dev]'"
  exit 1
fi
if [[ ! -d web/node_modules ]]; then
  npm install --prefix web
fi
if [[ ! -d node_modules ]]; then
  npm install
fi
echo "Kiln UI  http://127.0.0.1:5173"
echo "Kiln API http://127.0.0.1:8787"
echo "mlx      http://127.0.0.1:8081  (npm run start:mlx — selected local MLX model)"
echo "mtplx    http://127.0.0.1:8082  (npm run start:mtplx — 4B ~52 tok/s; then MLX_BASE_URL=http://127.0.0.1:8082)"
npm run dev
