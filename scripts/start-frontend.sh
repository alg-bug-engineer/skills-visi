#!/usr/bin/env bash
# 启动前端 Vite 开发服务。
# 端口可用 FRONTEND_PORT 覆盖（默认 5173）。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="${ROOT_DIR}/frontend"
PORT="${FRONTEND_PORT:-5173}"
BACKEND_PORT="${BACKEND_PORT:-8000}"

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

export FRONTEND_PORT="${PORT}"
export VITE_API_TARGET="${VITE_API_TARGET:-http://127.0.0.1:${BACKEND_PORT}}"

cd "${FRONTEND_DIR}"
if [ ! -d "node_modules" ]; then
  echo "▶ 未检测到 node_modules，执行 npm install…"
  npm install
fi

echo "▶ 开发模式：vite dev @ 0.0.0.0:${PORT}"
echo "▶ 本地访问 http://localhost:${PORT}（API → ${VITE_API_TARGET}）"
exec npm run dev -- --host 0.0.0.0 --port "${PORT}" --strictPort
