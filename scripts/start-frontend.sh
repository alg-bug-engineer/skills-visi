#!/usr/bin/env bash
# 启动前端（Vite dev server 或 ECS 公网 preview）。
# 端口可用 FRONTEND_PORT 覆盖（默认 5173）。
# ECS 公网：export PUBLIC_HOST=8.149.232.39 ECS_PUBLIC_ACCESS=1
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

# shellcheck source=resolve-public-host.sh
source "${SCRIPT_DIR}/resolve-public-host.sh"

PUBLIC_HOST="${PUBLIC_HOST:-$(resolve_public_host || true)}"
export FRONTEND_PORT="${PORT}"
export VITE_API_TARGET="${VITE_API_TARGET:-http://127.0.0.1:${BACKEND_PORT}}"

if [ -n "${PUBLIC_HOST}" ]; then
  export PUBLIC_HOST
  export VITE_DEV_PUBLIC_HOST="${PUBLIC_HOST}"
  export ECS_PUBLIC_ACCESS="${ECS_PUBLIC_ACCESS:-1}"
else
  export ECS_PUBLIC_ACCESS="${ECS_PUBLIC_ACCESS:-0}"
fi

cd "${FRONTEND_DIR}"
if [ ! -d "node_modules" ]; then
  echo "▶ 未检测到 node_modules，执行 npm install…"
  npm install
fi

print_access_banner "${PORT}" "${BACKEND_PORT}"
print_firewall_hints "${PORT}"

if [ "${ECS_PUBLIC_ACCESS}" = "1" ]; then
  if [ -z "${PUBLIC_HOST}" ]; then
    echo "✗ ECS 公网模式须设置 PUBLIC_HOST，例如："
    echo "    export PUBLIC_HOST=8.149.232.39 ECS_PUBLIC_ACCESS=1"
    exit 1
  fi
  echo "▶ 公网模式：npm run build && vite preview @ 0.0.0.0:${PORT}"
  echo "▶ 页面 origin：http://${PUBLIC_HOST}:${PORT}"
  npm run build
  exec npm run preview -- --host 0.0.0.0 --port "${PORT}" --strictPort
fi

echo "▶ 开发模式：vite dev @ 0.0.0.0:${PORT}"
if [ -n "${PUBLIC_HOST}" ]; then
  echo "▶ 公网请访问 http://${PUBLIC_HOST}:${PORT}（HMR/origin 已指向公网 IP）"
fi
exec npm run dev -- --host 0.0.0.0 --port "${PORT}" --strictPort
