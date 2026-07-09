#!/usr/bin/env bash
# 一键启动前后端：后端后台运行并等待健康，前端前台运行。
# Ctrl+C 时同时停止前后端。端口可用 BACKEND_PORT / FRONTEND_PORT 覆盖。
#
# ECS 公网访问（在你自己电脑浏览器打开，不要用 localhost）：
#   export PUBLIC_HOST=8.149.232.39
#   export ECS_PUBLIC_ACCESS=1
#   bash scripts/start-all.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
LOG_DIR="${ROOT_DIR}/logs"
mkdir -p "${LOG_DIR}"
BACKEND_LOG="${LOG_DIR}/backend-dev.log"

BACKEND_PID=""

# shellcheck source=resolve-public-host.sh
source "${SCRIPT_DIR}/resolve-public-host.sh"

if [ -z "${PUBLIC_HOST:-}" ]; then
  PUBLIC_HOST="$(resolve_public_host || true)"
fi
if [ -n "${PUBLIC_HOST}" ]; then
  export PUBLIC_HOST
  export ECS_PUBLIC_ACCESS="${ECS_PUBLIC_ACCESS:-1}"
  echo "▶ 公网部署 PUBLIC_HOST=${PUBLIC_HOST} ECS_PUBLIC_ACCESS=${ECS_PUBLIC_ACCESS}"
else
  export ECS_PUBLIC_ACCESS="${ECS_PUBLIC_ACCESS:-0}"
fi

cleanup() {
  echo ""
  echo "■ 正在停止前后端…"
  if [ -n "${BACKEND_PID}" ]; then
    kill "${BACKEND_PID}" 2>/dev/null || true
  fi
  for port in "${BACKEND_PORT}" "${FRONTEND_PORT}"; do
    local pids
    pids="$(lsof -ti "tcp:${port}" 2>/dev/null || true)"
    if [ -n "${pids}" ]; then
      # shellcheck disable=SC2086
      kill -9 ${pids} 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT INT TERM

echo "▶ 启动后端（后台，日志 → ${BACKEND_LOG}）"
BACKEND_PORT="${BACKEND_PORT}" "${SCRIPT_DIR}/start-backend.sh" >"${BACKEND_LOG}" 2>&1 &
BACKEND_PID=$!

echo -n "▶ 等待后端健康检查 http://127.0.0.1:${BACKEND_PORT}/api/v1/health "
for _ in $(seq 1 40); do
  if curl -sf "http://127.0.0.1:${BACKEND_PORT}/api/v1/health" >/dev/null 2>&1; then
    echo "✓"
    break
  fi
  if ! kill -0 "${BACKEND_PID}" 2>/dev/null; then
    echo "✗"
    echo "✗ 后端进程已退出，请查看日志：${BACKEND_LOG}"
    exit 1
  fi
  echo -n "."
  sleep 1
done

verify_port_listening "${BACKEND_PORT}" "后端" || true

echo "▶ 启动前端（前台，Ctrl+C 停止前后端）"
BACKEND_PORT="${BACKEND_PORT}" FRONTEND_PORT="${FRONTEND_PORT}" PUBLIC_HOST="${PUBLIC_HOST:-}" ECS_PUBLIC_ACCESS="${ECS_PUBLIC_ACCESS:-0}" "${SCRIPT_DIR}/start-frontend.sh"
