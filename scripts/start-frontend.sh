#!/usr/bin/env bash
# 启动前端（Vite dev server）。
# 启动前探测端口，被占则 kill 再启动。
# 端口可用 FRONTEND_PORT 覆盖（默认 5173）。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="${ROOT_DIR}/frontend"
PORT="${FRONTEND_PORT:-5173}"

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

cd "${FRONTEND_DIR}"
if [ ! -d "node_modules" ]; then
  echo "▶ 未检测到 node_modules，执行 npm install…"
  npm install
fi

echo "▶ 启动前端 http://0.0.0.0:${PORT}  （dev 代理 /api → 后端，支持公网 IP 访问）"
exec npm run dev -- --host 0.0.0.0 --port "${PORT}" --strictPort
