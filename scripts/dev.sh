#!/usr/bin/env bash
# 一键启动前后端开发服务（先清理端口残留进程）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT=8011
FRONTEND_PORT=5567
BACKEND_HOST=127.0.0.1
LOG_DIR="${ROOT}/.dev-logs"
BACKEND_LOG="${LOG_DIR}/backend.log"
FRONTEND_LOG="${LOG_DIR}/frontend.log"
PID_FILE="${LOG_DIR}/pids"

mkdir -p "$LOG_DIR"

log() {
  printf '[dev] %s\n' "$*"
}

kill_port() {
  local port=$1
  local name=$2
  local pids=""

  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -ti "tcp:${port}" -sTCP:LISTEN 2>/dev/null || true)"
  fi

  if [[ -z "$pids" ]]; then
    log "端口 ${port} (${name}) 无残留进程"
    return 0
  fi

  log "端口 ${port} (${name}) 发现残留进程: ${pids}，正在终止…"
  # shellcheck disable=SC2086
  kill ${pids} 2>/dev/null || true
  sleep 1

  pids="$(lsof -ti "tcp:${port}" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    log "强制终止端口 ${port} 进程: ${pids}"
    # shellcheck disable=SC2086
    kill -9 ${pids} 2>/dev/null || true
    sleep 0.5
  fi

  log "端口 ${port} 已清理"
}

stop_from_pid_file() {
  if [[ ! -f "$PID_FILE" ]]; then
    return 0
  fi
  while read -r pid name; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      log "停止上次启动的 ${name} (pid=${pid})"
      kill "$pid" 2>/dev/null || true
    fi
  done < "$PID_FILE"
  rm -f "$PID_FILE"
}

cleanup() {
  log "正在停止服务…"
  if [[ -n "${BACKEND_PID:-}" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [[ -n "${FRONTEND_PID:-}" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
}

trap cleanup EXIT INT TERM

log "项目根目录: ${ROOT}"
log "后端: http://${BACKEND_HOST}:${BACKEND_PORT}"
log "前端: http://127.0.0.1:${FRONTEND_PORT}"

stop_from_pid_file
kill_port "$BACKEND_PORT" "backend"
kill_port "$FRONTEND_PORT" "frontend"

# --- 后端 ---
if [[ ! -d "${ROOT}/backend/.venv" ]]; then
  log "未找到 backend/.venv，请先执行: cd backend && python3 -m venv .venv && pip install -e '.[dev]'"
  exit 1
fi

# shellcheck disable=SC1091
source "${ROOT}/backend/.venv/bin/activate"

log "启动后端 (uvicorn)…"
cd "${ROOT}/backend"
nohup uvicorn intersection_agent.main:app \
  --host "$BACKEND_HOST" \
  --port "$BACKEND_PORT" \
  >"$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

# 等待健康检查
for i in $(seq 1 30); do
  if curl -sf "http://${BACKEND_HOST}:${BACKEND_PORT}/health" >/dev/null 2>&1; then
    log "后端就绪 (pid=${BACKEND_PID})"
    break
  fi
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    log "后端启动失败，日志:"
    tail -n 30 "$BACKEND_LOG" || true
    exit 1
  fi
  if [[ "$i" -eq 30 ]]; then
    log "后端健康检查超时，日志:"
    tail -n 30 "$BACKEND_LOG" || true
    exit 1
  fi
  sleep 0.5
done

# --- 前端 ---
if [[ ! -d "${ROOT}/frontend/node_modules" ]]; then
  log "安装前端依赖…"
  cd "${ROOT}/frontend"
  npm install
fi

log "启动前端 (vite)…"
cd "${ROOT}/frontend"
export VITE_DEV_PROXY_TARGET="http://${BACKEND_HOST}:${BACKEND_PORT}"
export VITE_DEBUG_LOG=1
nohup npm run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort \
  >"$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!

for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${FRONTEND_PORT}/" >/dev/null 2>&1; then
    log "前端就绪 (pid=${FRONTEND_PID})"
    break
  fi
  if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    log "前端启动失败，日志:"
    tail -n 30 "$FRONTEND_LOG" || true
    exit 1
  fi
  if [[ "$i" -eq 30 ]]; then
    log "前端启动超时，日志:"
    tail -n 30 "$FRONTEND_LOG" || true
    exit 1
  fi
  sleep 0.5
done

{
  echo "$BACKEND_PID backend"
  echo "$FRONTEND_PID frontend"
} >"$PID_FILE"

log "=========================================="
log "  前端  http://127.0.0.1:${FRONTEND_PORT}"
log "  后端  http://${BACKEND_HOST}:${BACKEND_PORT}/health"
log "  日志  ${LOG_DIR}/"
log "=========================================="
log "按 Ctrl+C 停止前后端"

tail -f "$BACKEND_LOG" "$FRONTEND_LOG"
