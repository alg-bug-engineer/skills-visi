#!/usr/bin/env bash
# 启动扫描 API（默认 8100）。前端在 frontend/ 下 `npm run dev` 单独起。
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
PY="${REGION_SCAN_PYTHON:-$HERE/../backend/.venv/bin/python}"
PORT="${REGION_SCAN_PORT:-8100}"

cd "$HERE"
exec "$PY" -m uvicorn region_scan.api:app --host 0.0.0.0 --port "$PORT" "$@"
