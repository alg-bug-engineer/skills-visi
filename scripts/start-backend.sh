#!/usr/bin/env bash
# 启动后端 API（FastAPI + uvicorn）。
# 启动前探测端口，被占则 kill 再启动。
# 端口可用 BACKEND_PORT 覆盖（默认 8000）。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PORT="${BACKEND_PORT:-8000}"

free_port() {
  local port="$1"
  local pids
  pids="$(lsof -ti "tcp:${port}" 2>/dev/null || true)"
  if [ -n "${pids}" ]; then
    echo "⚠️  端口 ${port} 被占用（PID: ${pids}），正在结束…"
    # shellcheck disable=SC2086
    kill -9 ${pids} 2>/dev/null || true
    sleep 1
  fi
}

free_port "${PORT}"

cd "${ROOT_DIR}"
if [ ! -d ".venv" ]; then
  echo "✗ 未找到 .venv，请先创建虚拟环境（python -m venv .venv && .venv/bin/pip install -r requirements.txt）"
  exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "▶ 启动后端 http://localhost:${PORT}  （/api/v1/health 健康检查）"
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" --reload
